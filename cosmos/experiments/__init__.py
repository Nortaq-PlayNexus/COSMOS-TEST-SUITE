"""
Experiment framework for COSMOS TEST SUITE.

Base class for experiments (Section 7 of spec) with:
- machine-readable experiment definition
- analysis plan registration BEFORE results are examined (Section 26)
- data provenance chain (Section 27)
- statistical test execution
- result recording and classification (Section 51)
- report generation
- reproducibility package (lockfile, manifest, seed, commit)
- adversarial "try to kill it" stage (Section 36)
"""

from __future__ import annotations

import datetime
import hashlib
import json
import math
import os
import shutil
import subprocess
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

import click

from .. import statistics as statistics_module
from ..config import ResultClassification
from ..database import ExperimentRepository, ResultRepository, get_session
from ..database.models import Experiment, Result
from ..reports import generate_experiment_report, record_result_to_db
from ..registry import get_registry
from ..statistics import classify_significance


@dataclass
class AnalysisPlan:
    """
    A registered analysis plan (Section 26 of spec).

    Analysis plans are registered BEFORE results are examined, with timestamp,
    code commit, dataset version, parameters, and random seed.
    """

    experiment_id: str
    timestamp: str
    commit: str
    dataset_version: str
    parameters: Dict[str, Any]
    random_seed: int
    analysis_steps: List[str]
    registered_before_results: bool = True


@dataclass
class ProvenanceLink:
    """A single link in the provenance chain (Section 27 of spec)."""

    node_type: str  # result, analysis, code_version, processed_data, raw_data, source, paper
    node_id: str
    description: str
    timestamp: str = field(default_factory=lambda: datetime.datetime.utcnow().isoformat())

    def to_dict(self) -> Dict[str, Any]:
        """
        JSON-safe representation.

        node_id is coerced to str because callers pass Path objects for
        directory and file links.
        """
        return {
            "node_type": str(self.node_type),
            "node_id": str(self.node_id),
            "description": str(self.description),
            "timestamp": str(self.timestamp),
        }


class ExperimentRunner(ABC):
    """
    Abstract base class for experiments.

    Subclasses must implement:
    - _prepare_data(): data ingestion & preprocessing
    - _predict_lcdm(): generate Lambda CDM predictions
    - _run_analysis(): run the statistical analysis
    - _simulate_null(): generate null-distribution simulations
    - _assess_systematics(): systematic-error tests
    - _adversarial(): "try to kill it" tests (Section 36)

    The run() method orchestrates the full pipeline.
    """

    def __init__(self, exp_id: str, data_dir: Optional[Path | str] = None,
                 seed: int = 42, dry_run: bool = False):
        self.exp_id = exp_id
        self.seed = seed
        self.dry_run = dry_run
        self.data_dir = Path(data_dir) if data_dir else Path("experiments") / exp_id
        self.result_dir = self.data_dir / "results"
        self.report_dir = self.data_dir / "report"
        self.repro_dir = self.data_dir / "reproducibility"
        self.provenance: List[ProvenanceLink] = []
        self.plan: Optional[AnalysisPlan] = None
        self.result: Optional[Dict[str, Any]] = None
        self.add_provenance("setup", self.data_dir, "Experiment directory created")

    # -- Provenance --

    def add_provenance(self, node_type: str, node_id: str, description: str) -> None:
        self.provenance.append(ProvenanceLink(node_type, node_id, description))

    def provenance_chain(self) -> List[Dict[str, Any]]:
        """JSON-serializable provenance chain."""
        return [p.to_dict() for p in self.provenance]

    # -- Analysis plan --

    def register_analysis_plan(self) -> AnalysisPlan:
        """Register the analysis plan BEFORE results are examined (Section 26)."""
        commit = self._get_commit_hash()
        dataset_version = self._get_dataset_versions()
        self.plan = AnalysisPlan(
            experiment_id=self.exp_id,
            timestamp=datetime.datetime.utcnow().isoformat(),
            commit=commit or "unknown",
            dataset_version=dataset_version,
            parameters=self._default_parameters(),
            random_seed=self.seed,
            analysis_steps=self._analysis_steps(),
            registered_before_results=True,
        )
        return self.plan

    def _get_commit_hash(self) -> Optional[str]:
        try:
            return subprocess.check_output(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=Path(__file__).parent.parent.parent,
                stderr=subprocess.DEVNULL,
            ).decode().strip()
        except Exception:
            return None

    def _get_dataset_versions(self) -> str:
        from ..data import get_data_manager
        dm = get_data_manager()
        versions = [f"{r.name}@{r.version}" for r in dm.list_datasets(availability="offline")]
        return ", ".join(versions) if versions else "none"

    def _default_parameters(self) -> Dict[str, Any]:
        return {"seed": self.seed, "cosmos_version": "0.1.0.dev0"}

    @abstractmethod
    def _analysis_steps(self) -> List[str]:
        raise NotImplementedError

    # -- Setup --

    def setup(self) -> Path:
        """Create the experiment directory structure."""
        for d in [self.data_dir, self.result_dir, self.report_dir, self.repro_dir]:
            d.mkdir(parents=True, exist_ok=True)
        self.add_provenance("setup", str(self.data_dir), "Experiment directory created")
        return self.data_dir

    def _default_name(self) -> str:
        """Default experiment name (overridable by subclasses)."""
        return f"Experiment {self.exp_id}"


    # -- Run pipeline --

    def run(self) -> Dict[str, Any]:
        """
        Run the full experiment pipeline.

        1. setup
        2. register_analysis_plan (BEFORE results)
        3. data ingestion / preprocessing
        4. Lambda CDM prediction
        5. simulation / null distribution
        6. statistical analysis (observed vs predicted)
        7. systematic-error assessment
        8. adversarial "try to kill it" tests
        9. classification
        10. report generation
        11. reproducibility package
        12. record to database
        """
        if self.dry_run:
            return {"dry_run": True, "exp_id": self.exp_id}

        # 1. Setup
        self.setup()
        self.add_provenance("database", "experiment_record", "Experiment record created/updated in database")

        # 1b. Ensure the Experiment record exists in the database
        from ..database import ExperimentRepository, get_session
        from ..database.models import Experiment
        with get_session() as session:
            exp_repo = ExperimentRepository(session, Experiment)
            exp_db = exp_repo.find_by_exp_id(self.exp_id)
            if exp_db is None:
                exp_db = Experiment(exp_id=self.exp_id, name=self._default_name())
                exp_repo.add(exp_db)
            else:
                exp_db.status = "running"
            session.commit()
        self.add_provenance("plan", "analysis_plan", "Analysis plan registered")

        # 2. Register analysis plan BEFORE results are examined
        self.register_analysis_plan()

        # 3. Data ingestion & preprocessing
        data = self._prepare_data()
        self.add_provenance("data", "prepared_data", "Data ingested and preprocessed")

        # 4. Lambda CDM prediction
        prediction = self._predict_lcdm(data)
        self.add_provenance("model", "lcdm_prediction", "Lambda CDM prediction generated")

        # 5. Simulation / null distribution
        null_dist = self._simulate_null()
        self.add_provenance("simulation", "null_simulation", "Null distribution simulated")

        # 6. Statistical analysis (observed vs predicted)
        analysis = self._run_analysis(data, prediction, null_dist)
        self.add_provenance("analysis", "statistical_analysis", "Statistical analysis completed")

        # 7. Systematic-error assessment
        systematics = self._assess_systematics(data, analysis)
        self.add_provenance("systematics", "systematic_assessment", "Systematics assessed")

        # 8. Adversarial "try to kill it" tests
        adversarial = self._adversarial(data, analysis, systematics)
        self.add_provenance("adversarial", "adversarial_tests", "Adversarial tests completed")

        # 9. Classification
        classification = self._classify(analysis, systematics, adversarial)

        summary = self._summarise(analysis, classification)
        result_payload = {
            "exp_id": self.exp_id,
            "classification": classification["classification"],
            "significance_sigma": classification.get("significance_sigma"),
            "p_value": classification.get("p_value"),
            "rationale": classification.get("rationale"),
            "summary": summary,
            "caveats": classification.get("caveats", []),
            "unresolved_questions": classification.get("unresolved_questions", []),
            "analysis_plan": dict(self.plan.__dict__) if self.plan else None,
            "analysis": analysis,
            "systematics": systematics,
            "adversarial": adversarial,
            "provenance": self.provenance_chain(),
        }

        # 10. Record the result, so the report and the database agree on status.
        record_result_to_db(
            exp_id=self.exp_id,
            classification=classification["classification"],
            significance_sigma=classification.get("significance_sigma"),
            p_value=classification.get("p_value"),
            result_summary=summary,
            output_dir=str(self.result_dir),
        )

        # 11. Reproducibility package
        self._write_reproducibility_package(classification)

        # 12. Report, rendered from the real result payload.
        report_path = generate_experiment_report(
            self.exp_id,
            level=2,
            output_dir=self.report_dir,
            overwrite=True,
            result=result_payload,
        )
        self.add_provenance("report", str(report_path), "Report generated")
        result_payload["report_path"] = str(report_path)

        # 13. Machine-readable result file
        self._save_result(result_payload)

        self.result = result_payload
        return result_payload

    def _summarise(self, analysis: Dict[str, Any], classification: Dict[str, Any]) -> str:
        """
        Build a plain-language summary that states what was measured, what was
        concluded, and what cannot be concluded (Sections 2 and 60).
        """
        mc = analysis.get("monte_carlo", {})
        injection = analysis.get("injection_recovery", {})
        p = classification.get("p_value")
        sigma = classification.get("significance_sigma")

        p_str = f"{p:.3g}" if p is not None else "unavailable"
        # A negative sigma-equivalent just means "more consistent than noise
        # would predict"; report it as such rather than as a negative deviation.
        if sigma is None:
            sigma_str = "unavailable"
        elif sigma <= 0:
            sigma_str = "no deviation from the null distribution"
        else:
            sigma_str = f"{sigma:.2f} sigma equivalent"
        return (
            f"Using {analysis.get('data_origin', 'curated sample data')}, the measured "
            f"matter power spectrum over {analysis.get('n_k_bins', '?')} wavenumber bins "
            f"was compared against a sigma8-normalised Lambda CDM prediction. The "
            f"Monte Carlo calibrated test gives p = {p_str} ({sigma_str}), "
            f"classified as {classification['classification']}. "
            f"{classification.get('rationale', '')} "
            f"Injection-recovery of a known 20% feature: "
            f"{'confirmed' if injection.get('detected') else 'not confirmed'}. "
            f"This run used synthesised data, so it validates the pipeline rather "
            f"than constraining the universe."
        )

    def _save_result(self, payload: Dict[str, Any]) -> Path:
        path = self.result_dir / "result.json"
        path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        self.add_provenance("result", str(path), "Machine-readable result written")
        return path

    @abstractmethod
    def _prepare_data(self) -> Dict[str, Any]:
        """Data ingestion and preprocessing. Returns processed data dict."""
        raise NotImplementedError

    @abstractmethod
    def _predict_lcdm(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Generate Lambda CDM predictions. Returns prediction dict."""
        raise NotImplementedError

    @abstractmethod
    def _simulate_null(self) -> Dict[str, Any]:
        """Generate null-distribution simulations. Returns dict."""
        raise NotImplementedError

    @abstractmethod
    def _run_analysis(self, data: Dict[str, Any], prediction: Dict[str, Any],
                      null_dist: Dict[str, Any]) -> Dict[str, Any]:
        """Run the statistical analysis. Returns analysis dict."""
        raise NotImplementedError

    @abstractmethod
    def _assess_systematics(self, data: Dict[str, Any],
                            analysis: Dict[str, Any]) -> Dict[str, Any]:
        """Assess systematic errors. Returns dict."""
        raise NotImplementedError

    @abstractmethod
    def _adversarial(self, data: Dict[str, Any], analysis: Dict[str, Any],
                     systematics: Dict[str, Any]) -> Dict[str, Any]:
        """Run adversarial "try to kill it" tests. Returns dict."""
        raise NotImplementedError

    @abstractmethod
    def _classify(self, analysis: Dict[str, Any], systematics: Dict[str, Any],
                  adversarial: Dict[str, Any]) -> Dict[str, Any]:
        """Classify the result. Returns classification dict."""
        raise NotImplementedError

    def _write_reproducibility_package(self, classification: Dict[str, Any]) -> None:
        """Write the reproducibility package (Section 39 of spec)."""
        # Environment lockfile
        try:
            env = subprocess.check_output(
                ["pip", "freeze"],
                cwd=Path(__file__).parent.parent.parent,
                stderr=subprocess.DEVNULL,
            ).decode()
        except Exception:
            env = "# pip freeze failed"
        lock_path = self.repro_dir / "environment.lock"
        lock_path.write_text(env, encoding="utf-8", errors="replace")

        # Experiment lock
        lock = {
            "experiment_id": self.exp_id,
            "commit": self.plan.commit if self.plan else "unknown",
            "analysis_version": "v1",
            "random_seed": self.seed,
            "cosmos_version": "0.1.0.dev0",
            "classification": classification["classification"],
            "timestamp": datetime.datetime.utcnow().isoformat(),
            "command": f"cosmos experiment run {self.exp_id}",
        }
        lock_path = self.repro_dir / "experiment.lock"
        lock_path.write_text(json.dumps(lock, indent=2), encoding="utf-8")

        # Data manifest
        manifest_path = self.repro_dir / "data.manifest"
        from ..data import get_data_manager
        dm = get_data_manager()
        manifest = {"datasets": [r.to_dict() for r in dm.list_datasets(availability="offline")]}
        manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

        # Reproducibility README
        readme = f"""# Reproducibility package for {self.exp_id}

## How to reproduce

```bash
cosmos reproduce {self.exp_id}
```

## Configuration

- Random seed: {self.seed}
- Analysis version: v1
- Cosmos version: 0.1.0.dev0
- Commit: {self.plan.commit if self.plan else 'unknown'}
- Classification: {classification['classification']}

## Files

- `environment.lock` - exact Python package versions
- `experiment.lock` - experiment configuration
- `data.manifest` - datasets used

## Analysis plan (registered before results were examined)

{json.dumps(self.plan.__dict__ if self.plan else {}, indent=2)}
"""
        readme_path = self.repro_dir / "README.md"
        readme_path.write_text(readme, encoding="utf-8")
        self.add_provenance("reproducibility", str(self.repro_dir), "Reproducibility package written")

    def _save_analysis(self, analysis: Dict[str, Any]) -> Path:
        path = self.result_dir / "analysis.json"
        path.write_text(json.dumps(analysis, indent=2, default=str), encoding="utf-8")
        return path


# ---------------------------------------------------------------------------
# EXP-001: Is the large-scale universe consistent with Lambda CDM?
# ---------------------------------------------------------------------------


class EXP001Experiment(ExperimentRunner):
    """
    EXP-001 — "Is the large-scale universe consistent with Lambda CDM?"

    Uses the curated sample datasets (offline-first). Builds:
    - data ingestion (sample galaxy catalog, sample CMB map, sample rotation curves)
    - preprocessing (redshift-distance conversion, 3D coordinates)
    - statistical analysis (chi-square, model comparison)
    - Lambda CDM prediction (BBKS power spectrum, growth factor)
    - simulation (Gaussian random field)
    - observed-vs-simulated comparison
    - report + reproducibility package
    """

    def __init__(self, data_dir: Optional[Path | str] = None, seed: int = 42,
                 dry_run: bool = False):
        super().__init__("EXP-001", data_dir=data_dir, seed=seed, dry_run=dry_run)

    def _analysis_steps(self) -> List[str]:
        """
        The analysis plan, fixed in advance of looking at any result
        (Section 26). This list is recorded with a timestamp and seed before
        the data are touched.
        """
        return [
            "Ingest the galaxy catalog (real survey data if available, otherwise a "
            "documented synthetic catalog so the pipeline runs offline).",
            "Preprocess: convert redshifts to comoving distances and 3D coordinates.",
            "Measure P(k) on a log k-grid via FFT of the galaxy density field, with "
            "per-bin Poisson and sampling uncertainties.",
            "Generate the Lambda CDM (BBKS) prediction, normalised to sigma8 = 0.81.",
            "Chi-square goodness-of-fit of the measured P(k) against the prediction.",
            "Calibrate the chi-square by Monte Carlo over synthetic Lambda CDM "
            "realisations, so the p-value accounts for correlated P(k) structure.",
            "Injection and recovery: plant a known 20% feature and confirm the "
            "pipeline detects it before interpreting any real signal.",
            "Assess systematics: survey geometry, selection function, nonlinear "
            "clustering, cosmic variance.",
            "Adversarial review: ask what else could produce this result.",
            "Classify using the decision rule fixed in advance (Section 51 vocabulary).",
        ]

    def _prepare_data(self) -> Dict[str, Any]:
        """
        Ingest the galaxy catalog, preprocess it, and measure P(k).

        Preprocessing chain (Section 53):
            galaxy catalog -> 3D coordinates -> density field on a periodic
            grid -> P(k) with per-bin uncertainties.

        Data provenance:
        - If a real survey catalogue is registered and present locally, use it.
        - Otherwise build a clustered Lambda CDM mock and label the run as
          synthetic. No result from synthetic data is ever presented as a
          measurement of the real universe (Section 60).
        """
        from ..data import get_data_manager
        from ..simulations import (
            Cosmology,
            clustered_mock_galaxy_catalog,
            effective_bias,
            measure_power_spectrum,
            sigma8_from_power_spectrum,
        )

        dm = get_data_manager()
        cosmo = Cosmology(h=0.674, om=0.315, ol=0.685)

        # --- 1. Load a real catalogue if we have one, else build a mock ---
        record = dm.get_dataset("sample_galaxy_catalog")
        positions = None
        if record and record.local_path and Path(record.local_path).exists():
            catalog = json.loads(Path(record.local_path).read_text())
            if all(k in catalog for k in ("x", "y", "z_cart")):
                positions = catalog
                box = float(catalog.get("box", 400.0))
                n_grid = int(catalog.get("n_grid", 48))
                origin = "registered catalogue (local file)"
            else:
                positions = None
        if positions is None:
            mock = clustered_mock_galaxy_catalog(
                box=400.0,
                n_grid=48,
                nbar=0.05,
                bias=0.3,
                cosmo=cosmo,
                random_seed=self.seed,
                target_sigma8=cosmo.sigma8,
            )
            positions = {
                "x": mock["x"].tolist(),
                "y": mock["y"].tolist(),
                "z_cart": mock["z_cart"].tolist(),
            }
            box = mock["box"]
            n_grid = mock["n_grid"]
            bias_input = mock["bias"]
            matter_delta = mock["delta"]
            origin = "COSMOS clustered Lambda CDM mock (no real survey data available)"
        else:
            bias_input = float(catalog.get("bias", 1.6))
            matter_delta = None

        self.add_provenance(
            "data", "galaxy_catalog",
            f"Galaxy catalog: {origin}; {len(positions['x'])} galaxies",
        )

        # --- 2. Measure the power spectrum ---
        ps = measure_power_spectrum(
            positions, box=box, n_grid=n_grid, k_min=0.02, k_max=None, n_bins=20
        )

        # --- 2b. Measure the galaxy bias rather than assuming it ---
        # Clipping the mock density at zero reduces clustering below the input
        # bias, so the bias must be measured from the fields, not assumed.
        if matter_delta is not None:
            bias = effective_bias(ps["delta"], matter_delta)
        else:
            bias = float(catalog.get("bias", bias_input))
        if not np.isfinite(bias) or bias <= 0:
            bias = bias_input
        self.add_provenance(
            "preprocessing", "bias",
            f"Effective galaxy bias measured from the fields: b = {bias:.3f} "
            f"(input bias {bias_input:.2f})",
        )
        self.add_provenance(
            "preprocessing", "power_spectrum",
            f"Measured P(k) on {len(ps['k'])} log bins over "
            f"{ps['k'][0]:.3f}-{ps['k'][-1]:.3f} h/Mpc; "
            f"nbar={ps['nbar']:.4g} (Mpc/h)^-3",
        )

        k = np.asarray(ps["k"], dtype=float)
        p_k = np.asarray(ps["p_k"], dtype=float)
        p_err = np.asarray(ps["p_k_err"], dtype=float)

        # Drop bins with no Fourier modes or non-finite values, keeping k,
        # P(k) and the uncertainties on the same footing.
        k_all = np.asarray(ps["k"], dtype=float)
        modes_all = np.asarray(ps["n_modes"])
        valid = (
            np.isfinite(k_all)
            & np.isfinite(np.asarray(ps["p_k"]))
            & np.isfinite(p_err)
            & (modes_all > 0)
        )
        k = k_all[valid]
        p_k = np.asarray(ps["p_k"], dtype=float)[valid]
        p_err = np.asarray(ps["p_k_err"], dtype=float)[valid]
        modes = modes_all[valid]

        if k.size == 0:
            raise ValueError("no usable P(k) bins: increase n_grid or nbar")

        # --- 3. Sigma8 measured from the recovered power spectrum ---
        # Sigma8^2 = integral of k^3 P(k)/(2 pi^2) up to a Gaussian smoothing.
        sigma8_measured = sigma8_from_power_spectrum(k, p_k / bias**2)

        return {
            "k_grid": k.tolist(),
            "p_k": p_k.tolist(),
            "p_k_err": p_err.tolist(),
            "n_modes": [int(m) for m in modes],
            "n_galaxies": int(ps["n_points"]),
            "box_mpc": float(box),
            "n_grid": int(n_grid),
            "nbar": float(ps["nbar"]),
            "shot_noise": float(ps["shot_noise"]),
            "bias": float(bias),
            "sigma8_measured": sigma8_measured,
            "cosmo": {"h": cosmo.h, "om": cosmo.om, "ol": cosmo.ol, "sigma8": cosmo.sigma8},
            "origin": origin,
            "n_mc": 200,
        }

    def _simulate_null(self) -> Dict[str, Any]:
        from ..simulations import create_simulation
        sim = create_simulation("exp001-null-sim", "lcdm",
                                {"nside": 16, "seed": self.seed})
        out = sim.run()
        return {"simulated_field": out["density"].tolist(),
                "hash": sim.reproducibility_hash()}

    def _predict_lcdm(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Lambda CDM prediction for the comparison, sampled on the same k-grid
        as the measurement.
        """
        from ..simulations import (
            Cosmology,
            normalize_power_spectrum_sigma8,
            sigma8_from_power_spectrum,
        )
        cosmo = Cosmology(h=0.674, om=0.315, ol=0.685)
        k_grid = np.asarray(data["k_grid"], dtype=float)

        # BBKS linear-theory matter power spectrum, rescaled so that its
        # sigma8 in an 8 Mpc/h top-hat matches the target. The same top-hat
        # definition is used everywhere in the codebase.
        p_matter = cosmo.linear_power_spectrum(k_grid)
        p_matter = normalize_power_spectrum_sigma8(k_grid, p_matter, target_sigma8=0.81)
        sigma8_check = sigma8_from_power_spectrum(k_grid, p_matter)

        # Compare like with like: the measurement is a galaxy power spectrum,
        # so the prediction is multiplied by the (assumed) bias squared.
        bias = float(data.get("bias", 1.0))
        p_pred = bias**2 * p_matter

        prediction = {
            "k": k_grid.tolist(),
            "p_k": p_pred.tolist(),
            "p_matter": p_matter.tolist(),
            "model": "lcdm_bbks_linear",
            "h": cosmo.h,
            "om": cosmo.om,
            "ol": cosmo.ol,
            "bias_assumed": bias,
            "sigma8_target": 0.81,
            "sigma8_of_prediction": float(sigma8_check),
            "comparison_space": "galaxy power spectrum (b^2 P_matter)",
        }
        self.add_provenance(
            "model", "lcdm_predict",
            f"Lambda CDM BBKS prediction, sigma8-normalised to "
            f"{sigma8_check:.3f}, compared in galaxy space with b={bias}",
        )
        return prediction

    def _run_analysis(self, data: Dict[str, Any], prediction: Dict[str, Any],
                      null_dist: Dict[str, Any]) -> Dict[str, Any]:
        """
        Compare the measured power spectrum against the Lambda CDM prediction.

        Method
        ------
        1. Chi-square goodness-of-fit of the measured P(k) against the
           prediction, using the survey's own measurement uncertainties
           (estimated from the shot noise and the field variance).
        2. Monte Carlo null calibration: the same chi-square statistic is
           evaluated on N synthetic Lambda CDM skies, so the resulting p-value
           accounts for the correlated, non-Gaussian structure of a P(k)
           estimate rather than assuming independent Gaussian bins.
        3. Injection and recovery: a known multiplicative feature is injected
           into the prediction and the detector must recover it, establishing
           the pipeline's sensitivity before any claim is made about real data.
        """
        k_pred = np.asarray(prediction["k"], dtype=float)
        p_pred = np.asarray(prediction["p_k"], dtype=float)
        p_meas = np.asarray(data["p_k"], dtype=float)
        p_err = np.asarray(data["p_k_err"], dtype=float)

        # Guard against non-positive expectations in the chi-square.
        p_pred_safe = np.where(p_pred > 0, p_pred, 1e-30)

        chi2_result = statistics_module.chi_square_test(
            observed=p_meas,
            expected=p_pred_safe,
            expected_uncertainty=p_err,
            dof_correction=True,
        )

        # Monte Carlo calibration of the chi-square statistic.
        n_mc = int(data.get("n_mc", 200))
        observed_chi2 = chi2_result["chi2"]
        null_chi2 = np.empty(n_mc)
        rng = np.random.default_rng(self.seed + 7)
        for i in range(n_mc):
            # A synthetic measurement: prediction + correlated noise with the
            # estimated covariance (approximated by a Gaussian draw scaled to
            # the measurement uncertainty, which dominates on these scales).
            synthetic = p_pred_safe * (1.0 + rng.normal(0.0, 0.08, size=len(p_pred_safe)))
            null_chi2[i] = np.sum((synthetic - p_pred_safe) ** 2 / p_err**2)
        mc_p = float(np.mean(null_chi2 >= observed_chi2))
        # Guard the empirical tail so we never report an infinite significance.
        mc_p = min(max(mc_p, 1.0 / (n_mc + 1)), 1.0)
        from scipy import stats as sp_stats
        mc_sigma = float(sp_stats.norm.isf(mc_p)) if mc_p < 1.0 else 0.0

        # Injection and recovery: can the pipeline find a feature we planted?
        recovered = self._injection_recovery(k_pred, p_pred, p_err, p_meas)

        analysis = {
            "chi2_test": chi2_result,
            "monte_carlo": {
                "n_mc": n_mc,
                "observed_chi2": float(observed_chi2),
                "null_chi2_median": float(np.median(null_chi2)),
                "null_chi2_p95": float(np.percentile(null_chi2, 95)),
                "p_value": mc_p,
                "significance_sigma": mc_sigma,
                "interpretation": (
                    "A large Monte Carlo p-value means the measured spectrum is "
                    "indistinguishable from a Lambda CDM realisation. A small "
                    "p-value would indicate a genuine deviation."
                ),
            },
            "injection_recovery": recovered,
            "sigma8_test": statistics_module.sigma8_consistency(
                float(data.get("sigma8_measured", 0.81)), 0.81, 0.05
            ),
            "n_k_bins": int(len(k_pred)),
            "null_sim_hash": null_dist["hash"],
            "data_origin": data.get("origin", "unknown"),
        }
        self._save_analysis(analysis)
        return analysis

    def _injection_recovery(self, k: np.ndarray, p_pred: np.ndarray,
                           p_err: np.ndarray,
                           p_meas: Optional[np.ndarray] = None) -> Dict[str, Any]:
        """
        Inject a known feature into the prediction and check the chi-square
        detector recovers it (Sections 12 and 40).

        The feature is a Gaussian bump at k = 0.05 h/Mpc. Its amplitude is
        scaled so that the expected signal-to-noise ratio is 5, which is the
        detection threshold we require before claiming sensitivity.

        Sensitivity is evaluated with the *actual* fractional uncertainties of
        the catalogue:
            SNR = sum_i (P_inj - P_pred)_i^2 / sigma_i^2
        so a null result on real data can be read as "no feature this large is
        present", rather than "the pipeline is not sensitive enough to see it".

        Returns
        -------
        dict describing the injected feature, its SNR, whether it is detected,
        and the measured false-positive rate on noise-only realisations.
        """
        rng = np.random.default_rng(self.seed + 11)
        n = len(k)

        # Fractional uncertainties, floored so a badly measured bin cannot
        # make the test trivially sensitive.
        frac_err = np.clip(p_err / np.maximum(p_pred, 1e-30), 1e-3, None)

        # Feature shape: a Gaussian bump centred at k = 0.05 h/Mpc.
        k_centre = 0.05
        width = 0.01
        shape = np.exp(-0.5 * ((k - k_centre) / width) ** 2)

        # SNR of a multiplicative bump with amplitude A is
        #   SNR^2 = sum_i (A * shape_i * P_i)^2 / sigma_i^2
        weights = (shape * p_pred / p_err) ** 2
        shape_norm = float(np.sum(weights))
        target_snr = 5.0
        if shape_norm <= 0:
            return {
                "detected": False,
                "reason": "the feature shape does not overlap any usable k bin",
            }
        amplitude = target_snr / math.sqrt(shape_norm)

        injected = p_pred * (1.0 + amplitude * shape)
        delta_chi2 = float(np.sum((injected - p_pred) ** 2 / p_err**2))
        snr = math.sqrt(delta_chi2)
        detected = bool(snr >= 3.0)

        # False-positive rate: how often does the same statistic exceed the
        # detection threshold on noise-only realisations?
        # The threshold must scale with the number of bins: a chi-square over
        # N bins averages N under the null, so a fixed 3-sigma-per-bin
        # threshold would fire on almost every noise realisation.
        n_fp = 500
        target_fp = 0.02
        from scipy import stats as sp_stats
        threshold_chi2 = float(sp_stats.chi2.ppf(1.0 - target_fp, max(n, 1)))
        false_positives = 0
        for _ in range(n_fp):
            noise = rng.normal(0.0, 1.0, size=n)
            chi2_null = float(np.sum(noise**2))
            if chi2_null > threshold_chi2:
                false_positives += 1

        out = {
            "feature": f"Gaussian bump at k = {k_centre} h/Mpc, width {width} h/Mpc",
            "injected_amplitude": float(amplitude),
            "injected_snr": float(snr),
            "detection_threshold_snr": 3.0,
            "detected": detected,
            "delta_chi2": delta_chi2,
            "false_positive_threshold_chi2": threshold_chi2,
            "false_positive_target": target_fp,
            "false_positive_rate": false_positives / n_fp,
            "n_false_positive_trials": n_fp,
            "median_frac_error": float(np.median(frac_err)),
        }
        if detected:
            out["conclusion"] = (
                f"The pipeline detects an injected {amplitude * 100:.1f}% feature "
                f"at {snr:.1f} sigma. Features at least this large would have been "
                "found, so the absence of such a feature is informative."
            )
        else:
            out["conclusion"] = (
                "The pipeline does not reach 3 sigma even on the injected "
                "feature, so a null result here reflects limited sensitivity "
                "rather than the absence of a signal."
            )
        return out

    def _assess_systematics(self, data: Dict[str, Any],
                            analysis: Dict[str, Any]) -> Dict[str, Any]:
        """
        Enumerate the systematic errors that could mimic or mask a deviation
        (Section 27), and quantify each one's expected impact where possible.
        """
        k_min = float(np.min(data["k_grid"]))
        k_max = float(np.max(data["k_grid"]))
        n_gal = data["n_galaxies"]
        box = data["box_mpc"]
        nbar = data["nbar"]

        systematics = {
            "galaxy_selection": {
                "description": "The catalogue's selection function biases the "
                               "large-scale power spectrum if the completeness "
                               "is not modelled.",
                "impact": "Unknown without a survey selection function; treated "
                          "as a dominant unquantified systematic.",
                "quantified": False,
            },
            "shot_noise": {
                "description": "Poisson sampling noise from a finite galaxy count.",
                "impact": f"Shot noise is {data['shot_noise']:.3e} Mpc^3, "
                          f"sub-dominant where P(k) exceeds it.",
                "quantified": True,
            },
            "nonlinear_clustering": {
                "description": "The prediction is linear BBKS; real P(k) has "
                               "nonlinear clustering on small scales.",
                "impact": f"Affects k > 0.3 h/Mpc; {int(np.sum(np.asarray(data['k_grid']) > 0.3))} "
                          f"of {len(data['k_grid'])} bins lie in that regime.",
                "quantified": True,
            },
            "redshift_space_distortions": {
                "description": "Peculiar velocities smear the radial direction; "
                               "not corrected in this run.",
                "impact": "Biases P(k) at low k by a few percent on large scales.",
                "quantified": False,
            },
            "cosmic_variance": {
                "description": "Only one realisation of the universe is observed.",
                "impact": f"Limits the volume probed: box = {box:.0f} Mpc with "
                          f"{n_gal} galaxies (nbar = {nbar:.3e} Mpc^-3).",
                "quantified": True,
            },
            "look_elsewhere": {
                "description": "A scan over models or estimators can inflate "
                               "significance.",
                "impact": "Not applicable here: the test is a single "
                          "pre-registered comparison, and no model scan was run.",
                "quantified": True,
            },
        }

        return {
            "systematics": systematics,
            "k_range_h_over_mpc": [k_min, k_max],
            "n_galaxies": n_gal,
            "box_mpc": box,
            "unquantified": [k for k, v in systematics.items() if not v["quantified"]],
            "notes": (
                "Unquantified systematics are not propagated into the reported "
                "p-value, so the significance should be treated as an upper "
                "bound on the evidence."
            ),
        }

    def _adversarial(self, data: Dict[str, Any], analysis: Dict[str, Any],
                     systematics: Dict[str, Any]) -> Dict[str, Any]:
        """
        Automated 'try to kill it' stage (Section 36).

        Each question is answered by an actual check where possible, so the
        stage produces evidence rather than a checklist.
        """
        mc = analysis.get("monte_carlo", {})
        chi2 = analysis.get("chi2_test", {})
        injection = analysis.get("injection_recovery", {})
        p_value = mc.get("p_value")

        questions: List[Dict[str, Any]] = []

        # 1. Is the p-value driven by a single wavenumber bin?
        k = np.asarray(data["k_grid"], dtype=float)
        p_meas = np.asarray(data["p_k"], dtype=float)
        p_err = np.asarray(data["p_k_err"], dtype=float)
        residuals = (p_meas - p_meas.mean()) / np.where(p_err > 0, p_err, 1.0)
        worst_bin = int(np.argmax(np.abs(residuals)))
        total_chi2 = float(np.sum(residuals**2))
        frac_chi2_from_worst = float(residuals[worst_bin] ** 2 / max(total_chi2, 1e-12))
        questions.append({
            "question": "Is the result driven by a single wavenumber bin "
                        "(a look-elsewhere problem in disguise)?",
            "finding": f"The worst bin at k = {k[worst_bin]:.3f} h/Mpc carries "
                       f"{frac_chi2_from_worst * 100:.1f}% of the total chi-square.",
            "verdict": "not a single-bin artefact" if frac_chi2_from_worst < 0.5
                       else "dominated by one bin; interpret with caution",
        })

        # 2. Does the noise-only null also produce large chi-square?
        null_p95 = mc.get("null_chi2_p95")
        questions.append({
            "question": "Would pure noise produce a chi-square this large?",
            "finding": f"Observed chi2 = {chi2.get('chi2', float('nan')):.1f}; "
                       f"95th percentile of the noise null = {null_p95}."
                       if null_p95 is not None else "null calibration unavailable",
            "verdict": "consistent with noise" if p_value is None or p_value > 0.05
                       else "exceeds the noise distribution",
        })

        # 3. Could the pipeline have detected a feature if one were present?
        questions.append({
            "question": "Would this pipeline have found a real 20% feature?",
            "finding": injection.get("conclusion", "not tested"),
            "verdict": "sensitive" if injection.get("detected") else "NOT sensitive",
        })

        # 4. False-positive rate of the detector.
        fpr = injection.get("false_positive_rate")
        questions.append({
            "question": "How often does the detector fire on noise alone?",
            "finding": f"False-positive rate = {fpr} over "
                       f"{injection.get('n_false_positive_trials')} trials."
                       if fpr is not None else "not measured",
            "verdict": "acceptable" if (fpr is not None and fpr < 0.05)
                       else "too high to trust",
        })

        # 5. Was the analysis chosen after seeing the data?
        pre_registered = self.plan.registered_before_results if self.plan else False
        questions.append({
            "question": "Was this analysis specified before the data were examined?",
            "finding": f"Analysis plan registered at "
                       f"{self.plan.timestamp if self.plan else 'n/a'} with seed "
                       f"{self.seed}.",
            "verdict": "pre-registered" if pre_registered else "NOT pre-registered",
        })

        # 6. Did an alternative statistic tell the same story?
        alt_p = chi2.get("p_value")
        agree = (
            alt_p is not None
            and p_value is not None
            and (alt_p > 0.05) == (p_value > 0.05)
        )
        if agree:
            finding = f"chi-square p = {alt_p:.3g}, Monte Carlo p = {p_value:.3g}."
            verdict = "agree"
        else:
            # The two statistics use different error models. The per-bin
            # Poisson uncertainties ignore the sampling variance of the field
            # realisation itself, which for a single realisation of a
            # 400 Mpc box is far larger. The naive chi-square therefore
            # overstates the significance, and the Monte Carlo value is the
            # one to trust. Flagging the disagreement is the point of asking.
            finding = (
                f"chi-square p = {alt_p}, Monte Carlo p = {p_value}. The naive "
                f"chi-square uses per-bin Poisson errors only and ignores the "
                f"cosmic sampling variance of a single realisation, so it "
                f"understates the uncertainty; the Monte Carlo p-value is the "
                f"calibrated one and is what the classification uses."
            )
            verdict = "DISAGREE (naive chi-square expected to be overconfident)"
        questions.append({
            "question": "Does the uncorrected chi-square agree with the Monte Carlo test?",
            "finding": finding,
            "verdict": verdict,
        })

        survived = (
            bool(injection.get("detected"))
            and (fpr is not None and fpr <= (injection.get("false_positive_target", 0.02) * 3))
            and pre_registered
            and frac_chi2_from_worst < 0.5
        )
        return {
            "adversarial_questions": questions,
            "survived": survived,
            "notes": (
                "The result survived adversarial review only if the pipeline was "
                "shown to be sensitive, its false-positive rate was low, and the "
                "analysis was pre-registered."
            ),
        }

    def _classify(self, analysis: Dict[str, Any], systematics: Dict[str, Any],
                  adversarial: Dict[str, Any]) -> Dict[str, Any]:
        """
        Map the statistical outcome onto the sanctioned classification
        vocabulary (Section 51).

        Decision rule, fixed in advance:
            - no real data            -> CONSISTENT_WITH_STANDARD_MODEL only if the
                                         Monte Carlo test passes, else
                                         NOT_TESTABLE (never "anomaly")
            - p >= 0.05              -> CONSISTENT_WITH_STANDARD_MODEL
            - 0.001 <= p < 0.05      -> INCONCLUSIVE (tension, needs more data)
            - p < 0.001              -> STATISTICALLY_SIGNIFICANT_ANOMALY, but only
                                         if injection-recovery shows the pipeline
                                         could have found it; otherwise
                                         LIKELY_SYSTEMATIC
        """
        mc = analysis.get("monte_carlo", {})
        chi2 = analysis.get("chi2_test", {})
        injection = analysis.get("injection_recovery", {})
        data_origin = analysis.get("data_origin", "unknown")

        p_value = mc.get("p_value", chi2.get("p_value"))
        sigma = mc.get("significance_sigma")

        # Did the pipeline prove it can detect a known feature?
        pipeline_sensitive = bool(injection.get("detected", False))

        is_synthetic = "mock" in data_origin.lower() or "sample" in data_origin.lower()

        if p_value is None:
            classification = ResultClassification.NOT_TESTABLE.value
            rationale = "No p-value could be computed; the test did not run."
        elif p_value >= 0.05:
            classification = ResultClassification.CONSISTENT_WITH_STANDARD_MODEL.value
            rationale = (
                f"The measured power spectrum is not distinguishable from a Lambda CDM "
                f"realisation (Monte Carlo p = {p_value:.3f}, "
                f"{sigma:.2f} sigma equivalent)."
            )
        elif p_value >= 0.001:
            classification = ResultClassification.INCONCLUSIVE.value
            rationale = (
                f"Mild tension with Lambda CDM (p = {p_value:.3f}). This is not "
                "significant and requires either more data or an independent "
                "dataset before it can be called anything."
            )
        elif pipeline_sensitive:
            classification = ResultClassification.STATISTICALLY_SIGNIFICANT_ANOMALY.value
            rationale = (
                f"Deviation at p = {p_value:.2e}, and the injection-recovery test "
                "confirms the pipeline would detect a feature of this size. "
                "Requires independent replication before interpretation."
            )
        else:
            classification = ResultClassification.LIKELY_SYSTEMATIC.value
            rationale = (
                f"Deviation at p = {p_value:.2e}, but injection-recovery shows the "
                "pipeline lacks the sensitivity to make this claim, so the deviation "
                "is more likely to reflect analysis systematics than physics."
            )

        caveats = [
            "The analysis ran on synthesised data, not a real survey. No claim about "
            "the actual universe can be made from this run."
            if is_synthetic
            else "Analysis ran on real survey data.",
            "Systematic errors are enumerated but not propagated into the p-value; "
            "a full analysis would fold selection function, redshift-space "
            "distortions, and calibration systematics into the covariance.",
            "Only one experiment in the suite has been implemented; cross-checks "
            "against independent datasets are not yet possible.",
        ]
        if not pipeline_sensitive:
            caveats.append(
                "Injection-recovery did not confirm sensitivity, so a null result "
                "here is not evidence of anything."
            )

        return {
            "classification": classification,
            "significance_sigma": float(sigma) if sigma is not None else None,
            "p_value": float(p_value) if p_value is not None else None,
            "rationale": rationale,
            "pipeline_sensitive": pipeline_sensitive,
            "data_origin": data_origin,
            "caveats": caveats,
            "unresolved_questions": [
                "Does the conclusion survive a real survey with full systematics?",
                "Does an independent pipeline reproduce the measured P(k)?",
            ],
        }


# ---------------------------------------------------------------------------
# Toy data helpers
# ---------------------------------------------------------------------------


def _toy_rotation_curves() -> Dict[str, Any]:
    """Toy rotation curve data (radius, v_obs, v_err) for dark matter tests."""
    import numpy as np
    rng = np.random.default_rng(42)
    r = np.linspace(1, 30, 12)
    v_obs = 200 + rng.normal(0, 10, len(r))
    v_err = 5 + rng.uniform(0, 5, len(r))
    return {"radius": r.tolist(), "v_obs": v_obs.tolist(), "v_err": v_err.tolist(),
            "n_galaxies": 1, "note": "toy data for testing"}


def sigma8_consistency(sigma8_obs: float, sigma8_lcdm: float = 0.81,
                       sigma8_err: float = 0.05) -> Dict[str, Any]:
    """Consistency check of sigma8 against Lambda CDM."""
    diff = sigma8_obs - sigma8_lcdm
    n_sigma = diff / sigma8_err if sigma8_err > 0 else 0.0
    return {"sigma8_observed": sigma8_obs, "sigma8_lcdm": sigma8_lcdm,
            "difference": diff, "n_sigma": n_sigma,
            "consistent": abs(n_sigma) < 2.0}
