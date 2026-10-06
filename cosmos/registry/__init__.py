"""
Experiment registry for COSMOS TEST SUITE.

Implements the experiment registry described in Sections 7 and 46 of the
specification:

- Each experiment has a unique ID (EXP-001 ... EXP-016).
- Each experiment has a machine-readable definition:
  {id, name, hypothesis, null_model, alternative_models, datasets,
   predictions, tests, falsification_conditions, systematics, status}
- Experiments are scored and ranked by:
  data_availability, theoretical_importance, observational_leverage,
  reproducibility, computational_feasibility, falsifiability, potential_impact
- The registry tracks next_in_line and recommended experiments.

The registry is persisted in the database (ExperimentRegistry table) and in
a human-readable YAML file (config/experiment_registry.yaml).
"""

from __future__ import annotations

import datetime
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

from ..database import get_session
from ..database.models import EXPERIMENT_STATUS, Experiment, ExperimentRegistry


# ---------------------------------------------------------------------------
# Default experiment registry (Sections 7 and 54 of spec)
# ---------------------------------------------------------------------------

DEFAULT_REGISTRY: List[Dict[str, Any]] = [
    {
        "exp_id": "EXP-001",
        "name": "Cosmic web and large-scale structure vs Lambda CDM",
        "description": (
            "Reconstruct the cosmic web from a galaxy survey, compute the "
            "power spectrum and two-point correlation function, and compare "
            "against Lambda CDM simulations. Measures the homogeneity scale."
        ),
        "question_key": "large_scale_homogeneity",
        "order": 1,
        "status": "data_awaiting",
        "scores": {"data_availability": 0.8, "theoretical_importance": 0.9,
                   "observational_leverage": 0.8, "reproducibility": 0.9,
                   "computational_feasibility": 0.9, "falsifiability": 0.8,
                   "potential_impact": 0.8},
    },
    {
        "exp_id": "EXP-002",
        "name": "Large-scale isotropy and preferred direction",
        "description": (
            "Test whether the universe has a preferred direction using CMB "
            "temperature, galaxy counts, quasar distributions, and supernovae. "
            "Implements directional statistics, dipole/quadrupole measurements, "
            "and hemispherical comparisons with look-elsewhere correction."
        ),
        "question_key": "large_scale_isotropy",
        "order": 2,
        "status": "not_started",
        "scores": {"data_availability": 0.8, "theoretical_importance": 0.9,
                   "observational_leverage": 0.9, "reproducibility": 0.8,
                   "computational_feasibility": 0.9, "falsifiability": 0.9,
                   "potential_impact": 0.8},
    },
    {
        "exp_id": "EXP-003",
        "name": "Homogeneity scale measurement",
        "description": (
            "Measure whether statistical properties converge toward homogeneity "
            "with increasing scale using counts-in-spheres, fractal-dimension "
            "diagnostics, and the two-point correlation function."
        ),
        "question_key": "large_scale_homogeneity",
        "order": 3,
        "status": "not_started",
        "scores": {"data_availability": 0.7, "theoretical_importance": 0.9,
                   "observational_leverage": 0.8, "reproducibility": 0.9,
                   "computational_feasibility": 0.9, "falsifiability": 0.8,
                   "potential_impact": 0.8},
    },
    {
        "exp_id": "EXP-004",
        "name": "Cosmic web reconstruction",
        "description": (
            "Reconstruct the cosmic web (filaments, walls, clusters, voids) "
            "from a galaxy catalog using DisPerSE / watershed / friends-of-"
            "friends, and measure filament length distributions, void size "
            "distribution, and topology."
        ),
        "question_key": "large_scale_homogeneity",
        "order": 4,
        "status": "not_started",
        "scores": {"data_availability": 0.7, "theoretical_importance": 0.8,
                   "observational_leverage": 0.8, "reproducibility": 0.8,
                   "computational_feasibility": 0.8, "falsifiability": 0.8,
                   "potential_impact": 0.7},
    },
    {
        "exp_id": "EXP-005",
        "name": "Dark matter: particle vs modified gravity",
        "description": (
            "Compare Lambda CDM particle dark matter against MOND-like "
            "modified gravity using galaxy rotation curves, cluster dynamics, "
            "and weak lensing. Fit both models and compare predictive performance."
        ),
        "question_key": "dark_matter_particle",
        "order": 5,
        "status": "not_started",
        "scores": {"data_availability": 0.9, "theoretical_importance": 1.0,
                   "observational_leverage": 0.9, "reproducibility": 0.8,
                   "computational_feasibility": 0.8, "falsifiability": 0.9,
                   "potential_impact": 1.0},
    },
    {
        "exp_id": "EXP-006",
        "name": "Modified gravity model comparison",
        "description": (
            "Implement a model-comparison framework for GR + Lambda CDM, MOND, "
            "phenomenological modified gravity, and scalar-tensor models. "
            "Compare against rotation curves, lensing, clusters, growth, CMB, and GW."
        ),
        "question_key": "modified_gravity",
        "order": 6,
        "status": "not_started",
        "scores": {"data_availability": 0.8, "theoretical_importance": 1.0,
                   "observational_leverage": 0.8, "reproducibility": 0.7,
                   "computational_feasibility": 0.7, "falsifiability": 0.9,
                   "potential_impact": 0.9},
    },
    {
        "exp_id": "EXP-007",
        "name": "Dark energy: w, w0-wa, evolving models",
        "description": (
            "Test Lambda CDM versus constant-w versus w0-wa versus evolving "
            "dark energy using DESI BAO, CMB, supernovae, expansion history, "
            "growth, and weak lensing. Calculate likelihood, posterior, AIC, BIC."
        ),
        "question_key": "dark_energy_evolving",
        "order": 7,
        "status": "not_started",
        "scores": {"data_availability": 0.9, "theoretical_importance": 1.0,
                   "observational_leverage": 0.9, "reproducibility": 0.8,
                   "computational_feasibility": 0.8, "falsifiability": 0.9,
                   "potential_impact": 1.0},
    },
    {
        "exp_id": "EXP-008",
        "name": "Hubble tension analysis",
        "description": (
            "Dedicated Hubble-constant analysis comparing CMB-inferred H0, "
            "Cepheid distance ladder, Type Ia supernovae, TRGB, and standard "
            "sirens. Account for covariance and systematic uncertainty."
        ),
        "question_key": "hubble_tension",
        "order": 8,
        "status": "not_started",
        "scores": {"data_availability": 1.0, "theoretical_importance": 1.0,
                   "observational_leverage": 1.0, "reproducibility": 0.9,
                   "computational_feasibility": 0.9, "falsifiability": 1.0,
                   "potential_impact": 1.0},
    },
    {
        "exp_id": "EXP-009",
        "name": "Inflation signatures",
        "description": (
            "Investigate observational predictions of inflation: scalar spectral "
            "index, tensor-to-scalar ratio, non-Gaussianity, CMB B-modes. Compare "
            "inflationary model classes."
        ),
        "question_key": "cosmic_inflation",
        "order": 9,
        "status": "not_started",
        "scores": {"data_availability": 0.6, "theoretical_importance": 0.9,
                   "observational_leverage": 0.7, "reproducibility": 0.8,
                   "computational_feasibility": 0.8, "falsifiability": 0.8,
                   "potential_impact": 0.9},
    },
    {
        "exp_id": "EXP-010",
        "name": "CMB anomalies with look-elsewhere correction",
        "description": (
            "Search for CMB anomalies: large-scale alignments, hemispherical "
            "asymmetry, cold/hot spots, multipole relationships, non-Gaussian "
            "structures. CRITICAL: correct for the look-elsewhere effect via "
            "Monte Carlo null distributions."
        ),
        "question_key": "cmb_anomalies",
        "order": 10,
        "status": "not_started",
        "scores": {"data_availability": 0.8, "theoretical_importance": 0.9,
                   "observational_leverage": 0.9, "reproducibility": 0.9,
                   "computational_feasibility": 0.7, "falsifiability": 0.9,
                   "potential_impact": 0.9},
    },
    {
        "exp_id": "EXP-011",
        "name": "Multiverse / bubble collision signatures",
        "description": (
            "Treat multiverse hypotheses as speculative. Research published "
            "models with observable predictions (circular CMB patterns). First "
            "prove the detection algorithm recovers injected signals in "
            "simulations; then test real observations."
        ),
        "question_key": "bubble_collision",
        "order": 11,
        "status": "not_started",
        "scores": {"data_availability": 0.5, "theoretical_importance": 0.7,
                   "observational_leverage": 0.6, "reproducibility": 0.8,
                   "computational_feasibility": 0.7, "falsifiability": 0.6,
                   "potential_impact": 0.7},
    },
    {
        "exp_id": "EXP-012",
        "name": "Cosmic topology (matched circles)",
        "description": (
            "Investigate non-trivial cosmic topology via matched-circle searches "
            "and CMB correlation analysis on Planck/WMAP data, with simulated "
            "compact and simply-connected universes for false-positive testing."
        ),
        "question_key": "universe_topology",
        "order": 12,
        "status": "not_started",
        "scores": {"data_availability": 0.7, "theoretical_importance": 0.9,
                   "observational_leverage": 0.8, "reproducibility": 0.9,
                   "computational_feasibility": 0.6, "falsifiability": 0.9,
                   "potential_impact": 0.8},
    },
    {
        "exp_id": "EXP-013",
        "name": "Spatial repetition under various assumptions",
        "description": (
            "Investigate what different cosmological assumptions (curvature, "
            "topology, spatial extent, number of possible states, entropy) "
            "imply about repeated configurations. Do not claim another Earth "
            "exists; determine exactly which assumptions are required."
        ),
        "question_key": "spatial_repetition",
        "order": 13,
        "status": "not_started",
        "scores": {"data_availability": 0.4, "theoretical_importance": 0.6,
                   "observational_leverage": 0.5, "reproducibility": 0.9,
                   "computational_feasibility": 0.9, "falsifiability": 0.5,
                   "potential_impact": 0.5},
    },
    {
        "exp_id": "EXP-014",
        "name": "Large cosmic structures (superclusters, walls)",
        "description": (
            "Search large galaxy catalogs for superclusters, walls, filaments, "
            "giant arcs, and large voids. For every extreme structure compute "
            "expected maximum size from simulations and the look-elsewhere-"
            "corrected probability."
        ),
        "question_key": "large_structures",
        "order": 14,
        "status": "not_started",
        "scores": {"data_availability": 0.9, "theoretical_importance": 0.8,
                   "observational_leverage": 0.9, "reproducibility": 0.9,
                   "computational_feasibility": 0.7, "falsifiability": 0.9,
                   "potential_impact": 0.8},
    },
    {
        "exp_id": "EXP-015",
        "name": "General Relativity tests at cosmological scales",
        "description": (
            "Test GR against observations: gravitational lensing, black-hole "
            "observations, gravitational-wave propagation, binary systems, "
            "gravitational redshift, cosmological growth, strong-field effects."
        ),
        "question_key": "gr_at_cosmological_scales",
        "order": 15,
        "status": "not_started",
        "scores": {"data_availability": 0.9, "theoretical_importance": 1.0,
                   "observational_leverage": 0.9, "reproducibility": 0.9,
                   "computational_feasibility": 0.8, "falsifiability": 0.9,
                   "potential_impact": 1.0},
    },
    {
        "exp_id": "EXP-016",
        "name": "Gravitational-wave observations",
        "description": (
            "Integrate public LIGO/Virgo/KAGRA data: read strain data, "
            "preprocessing, whitening, noise characterization, matched filtering, "
            "parameter estimation, waveform comparison, and GR tests."
        ),
        "question_key": "gravitational_waves",
        "order": 16,
        "status": "not_started",
        "scores": {"data_availability": 0.8, "theoretical_importance": 0.9,
                   "observational_leverage": 0.9, "reproducibility": 0.9,
                   "computational_feasibility": 0.7, "falsifiability": 0.9,
                   "potential_impact": 0.9},
    },
]


# ---------------------------------------------------------------------------
# Machine-readable experiment definitions
# ---------------------------------------------------------------------------


def build_experiment_definition(exp_id: str) -> Dict[str, Any]:
    """
    Build the machine-readable definition for an experiment (Section 7 of spec).

    Example:
        {
          "id": "EXP-001",
          "name": "Cosmic topology",
          "hypothesis": "...",
          "null_model": "...",
          "alternative_models": [],
          "datasets": [],
          "predictions": [],
          "tests": [],
          "falsification_conditions": [],
          "systematics": [],
          "status": "not_started"
        }
    """
    definitions: Dict[str, Dict[str, Any]] = {
        "EXP-001": {
            "id": "EXP-001",
            "name": "Cosmic web and large-scale structure vs Lambda CDM",
            "hypothesis": (
                "The distribution of galaxies on large scales is consistent with "
                "the Lambda CDM prediction for the matter power spectrum and "
                "two-point correlation function."
            ),
            "null_model": (
                "No structure / white noise: galaxies distributed uniformly "
                "with Poisson shot noise."
            ),
            "alternative_models": [
                "Lambda CDM (standard model): P(k) from linear theory with "
                "transfer function; nonlinear corrections.",
                "Power-law power spectrum with different tilt (n_s != 0.965).",
                "Cutoff at large scales (inflation alternative).",
            ],
            "assumptions": [
                "Galaxy bias is scale-independent on the scales measured.",
                "Redshift-space distortions are modeled or mitigated.",
                "Selection function is known from the survey.",
            ],
            "datasets": ["DESI DR1", "SDSS DR16", "Euclid EDR (simulated)"],
            "preprocessing": [
                "Redshift-distance conversion to 3D coordinates.",
                "Angular mask application.",
                "Weighting for completeness and selection effects.",
                "Baryon acoustic oscillation smoothing.",
            ],
            "prediction": (
                "P(k) peaks at k ~ 0.02 h/Mpc (BAO scale); the two-point "
                "correlation function shows a BAO peak at r ~ 100 h^-1 Mpc; "
                "the universe becomes homogeneous for R > ~100 h^-1 Mpc."
            ),
            "statistical_test": (
                "Chi-square goodness-of-fit of measured P(k) to Lambda CDM "
                "prediction; Kolmogorov-Smirnov test of void size distribution "
                "against simulations; bootstrap confidence intervals on the "
                "homogeneity scale."
            ),
            "expected_result": (
                "Measured power spectrum consistent with Lambda CDM within "
                "measurement errors; homogeneity scale R_h ~ 70-100 h^-1 Mpc."
            ),
            "falsification_condition": (
                "Measured P(k) or correlation function deviates from Lambda "
                "CDM by > 5 sigma after accounting for systematics and "
                "look-elsewhere effects; homogeneity not achieved by "
                "R = 250 h^-1 Mpc."
            ),
            "uncertainty": [
                "Measurement (shot noise, survey geometry).",
                "Modeling (nonlinear clustering, redshift-space distortions).",
                "Cosmic variance on the largest scales.",
            ],
            "systematic_errors": [
                "Galaxy selection / completeness biases.",
                "Redshift errors and peculiar velocities.",
                "Evolution of the sample with redshift.",
                "Baryonic effects on small-scale clustering.",
            ],
            "result": None,
            "confidence": None,
            "reproducibility": {
                "random_seed": 42,
                "software_version": "0.1.0.dev0",
                "analysis_version": "v1",
            },
            "status": "data_awaiting",
        },
    }
    return definitions.get(exp_id, _generic_definition(exp_id))


def _generic_definition(exp_id: str) -> Dict[str, Any]:
    return {
        "id": exp_id,
        "name": "Experiment " + exp_id,
        "hypothesis": None,
        "null_model": None,
        "alternative_models": [],
        "assumptions": [],
        "datasets": [],
        "preprocessing": [],
        "prediction": None,
        "statistical_test": None,
        "expected_result": None,
        "falsification_condition": None,
        "uncertainty": [],
        "systematic_errors": [],
        "result": None,
        "confidence": None,
        "reproducibility": {"random_seed": 42, "software_version": "0.1.0.dev0"},
        "status": "not_started",
    }


# ---------------------------------------------------------------------------
# Registry classes
# ---------------------------------------------------------------------------


@dataclass
class Registry:
    """
    The experiment registry (Sections 7 and 46 of spec).

    Provides:
    - List all experiments with status
    - Priority scoring and ranking
    - Next-in-line recommendation
    - Machine-readable definitions
    - Persistence to YAML and database
    """

    experiments: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    registry_table: List[Dict[str, Any]] = field(default_factory=list)

    def __post_init__(self):
        if not self.experiments:
            for item in DEFAULT_REGISTRY:
                self.add_experiment(item["exp_id"], **{k: v for k, v in item.items() if k != "exp_id"})

    def __post_init__(self):
        if not self.experiments:
            for item in DEFAULT_REGISTRY:
                self.add_experiment(item["exp_id"], **{k: v for k, v in item.items() if k != "exp_id"})

    # NOTE: experiments loaded from YAML have no definition attached unless the
    # YAML itself carries one. build_experiment_definition() provides a
    # machine-readable definition for every known ID on demand.

    @classmethod
    def load_from_file(cls, path: Path | str) -> "Registry":
        """Load registry from a YAML file."""
        p = Path(path)
        with open(p) as f:
            data = yaml.safe_load(f)
        reg = cls()
        for item in data.get("experiments", []):
            reg.add_experiment(item["exp_id"], **{k: v for k, v in item.items() if k != "exp_id"})
        return reg

    def add_experiment(
        self,
        exp_id: str,
        name: str,
        description: Optional[str] = None,
        question_key: Optional[str] = None,
        order: int = 0,
        status: str = "not_started",
        scores: Optional[Dict[str, float]] = None,
        definition: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Add an experiment to the registry."""
        if exp_id in self.experiments:
            self.experiments[exp_id]["status"] = status
            self.experiments[exp_id]["order"] = order
            if scores:
                self.experiments[exp_id]["scores"] = scores
            self.experiments[exp_id]["definition"] = definition or build_experiment_definition(exp_id)
            self.experiments[exp_id]["updated_at"] = datetime.datetime.utcnow().isoformat()
            return self.experiments[exp_id]

        exp = {
            "exp_id": exp_id,
            "name": name,
            "description": description,
            "question_key": question_key,
            "order": order,
            "status": status,
            "scores": scores or self._default_scores(),
            "definition": definition or build_experiment_definition(exp_id),
            "started_at": None,
            "completed_at": None,
            "created_at": datetime.datetime.utcnow().isoformat(),
            "updated_at": datetime.datetime.utcnow().isoformat(),
        }
        self.experiments[exp_id] = exp
        return exp

    def _default_scores(self) -> Dict[str, float]:
        return {
            "data_availability": 0.5,
            "theoretical_importance": 0.7,
            "observational_leverage": 0.7,
            "reproducibility": 0.7,
            "computational_feasibility": 0.7,
            "falsifiability": 0.7,
            "potential_impact": 0.7,
        }

    def score(self, exp_id: str) -> float:
        """Compute the total priority score for an experiment (0-1)."""
        exp = self.experiments.get(exp_id)
        if exp is None:
            return 0.0
        scores = exp.get("scores", self._default_scores())
        return sum(scores.values()) / len(scores)

    def rank(self) -> List[Tuple[str, float]]:
        """Return experiments ranked by priority score (descending)."""
        return sorted(
            [(exp_id, self.score(exp_id)) for exp_id in self.experiments],
            key=lambda x: (-x[1], self.experiments[x[0]]["order"]),
        )

    def next_in_line(self) -> Optional[str]:
        """Return the highest-priority experiment that is not yet completed."""
        for exp_id, _ in self.rank():
            if self.experiments[exp_id]["status"] not in ("completed", "failed", "blocked"):
                return exp_id
        return None

    def recommended(self) -> List[str]:
        """Return experiments recommended for immediate work."""
        return [exp_id for exp_id, _ in self.rank() if self.score(exp_id) > 0.7]

    def list_by_status(self, status: str) -> List[str]:
        """Return experiment IDs with a given status."""
        return [exp_id for exp_id, exp in self.experiments.items() if exp["status"] == status]

    def get(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """Get an experiment by ID."""
        return self.experiments.get(exp_id)

    def update_status(self, exp_id: str, status: str) -> bool:
        """Update the status of an experiment."""
        if exp_id not in self.experiments:
            return False
        self.experiments[exp_id]["status"] = status
        now = datetime.datetime.utcnow().isoformat()
        if status in ("running",):
            self.experiments[exp_id]["started_at"] = now
        elif status in ("completed", "failed", "blocked"):
            self.experiments[exp_id]["completed_at"] = now
        self.experiments[exp_id]["updated_at"] = now
        return True

    def get_definition(self, exp_id: str) -> Optional[Dict[str, Any]]:
        """Get the machine-readable definition for an experiment."""
        exp = self.experiments.get(exp_id)
        return exp.get("definition") if exp else None

    def to_yaml(self, path: Path | str) -> None:
        """Save the registry to a YAML file."""
        p = Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        data = {
            "version": "0.1.0",
            "updated_at": datetime.datetime.utcnow().isoformat(),
            "experiments": [
                {
                    "exp_id": exp_id,
                    "name": exp["name"],
                    "description": exp.get("description"),
                    "question_key": exp.get("question_key"),
                    "order": exp["order"],
                    "status": exp["status"],
                    "scores": exp.get("scores"),
                    "definition": exp.get("definition"),
                }
                for exp_id, exp in self.experiments.items()
            ],
        }
        with open(p, "w") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    def sync_status_from_database(self, database_url: Optional[str] = None) -> None:
        """
        Pull live experiment status from the database into the in-memory
        registry. Never overwrites the YAML file (which holds the registered
        analysis plan); only refreshes status/result fields for display.
        """
        try:
            from ..database import ExperimentRepository, get_session
            from ..database.models import Experiment
            with get_session(database_url) as session:
                repo = ExperimentRepository(session, Experiment)
                for exp_db in session.query(Experiment).all():
                    entry = self.experiments.get(exp_db.exp_id)
                    if entry is None:
                        continue
                    if exp_db.status:
                        entry["status"] = exp_db.status
                    if exp_db.result_classification:
                        entry["result_classification"] = exp_db.result_classification
                    if exp_db.significance_sigma is not None:
                        entry["significance_sigma"] = exp_db.significance_sigma
                    if exp_db.result_summary:
                        entry["result_summary"] = exp_db.result_summary
                    if exp_db.end_date:
                        entry["completed_at"] = exp_db.end_date.isoformat()
        except Exception:
            # Status sync is best-effort; never break the CLI if the DB is absent.
            pass

    def sync_to_database(self, database_url: Optional[str] = None) -> None:
        """Synchronize the registry with the database."""
        from ..database import ExperimentRegistryRepository, ExperimentRepository
        with get_session(database_url) as session:
            reg_repo = ExperimentRegistryRepository(session, ExperimentRegistry)
            exp_repo = ExperimentRepository(session, Experiment)
            for exp_id, exp in self.experiments.items():
                # Registry entry
                reg = reg_repo.find_by_exp_id(exp_id)
                if reg is None:
                    reg_repo.add_experiment(
                        exp_id,
                        exp["name"],
                        description=exp.get("description"),
                        order=exp["order"],
                        scores=exp.get("scores"),
                    )
                else:
                    # Update registry entry fields
                    for key in ["name", "description", "order", "status"]:
                        if key in exp:
                            setattr(reg, key, exp[key])
                    for key, val in (exp.get("scores") or {}).items():
                        if hasattr(reg, key):
                            setattr(reg, key, val)
                # Experiment DB entry
                exp_db = exp_repo.find_by_exp_id(exp_id)
                if exp_db is None:
                    exp_db = Experiment(exp_id=exp_id, name=exp["name"], status=exp["status"])
                    exp_repo.add(exp_db)
                else:
                    exp_db.status = exp["status"]
                    exp_db.name = exp["name"]


# ---------------------------------------------------------------------------
# Default singleton
# ---------------------------------------------------------------------------

_default_registry: Optional[Registry] = None


def get_registry(database_url: Optional[str] = None) -> Registry:
    """
    Get the default registry.

    Statuses recorded in the database (e.g. a completed EXP-001 run) take
    precedence over the static YAML file, so the CLI reflects real run state.
    """
    global _default_registry
    if _default_registry is None:
        default_path = Path("config") / "experiment_registry.yaml"
        if default_path.exists():
            _default_registry = Registry.load_from_file(default_path)
        else:
            _default_registry = Registry()
            _default_registry.to_yaml(default_path)
    _default_registry.sync_status_from_database(database_url)
    return _default_registry


def reset_registry() -> None:
    """Reset the default registry (useful for testing)."""
    global _default_registry
    _default_registry = None
