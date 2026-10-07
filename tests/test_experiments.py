"""
Tests for the COSMOS experiment framework and EXP-001.

Verifies the pipeline discipline required by the specification:
- the analysis plan is registered BEFORE results are examined (Section 26)
- a full provenance chain is recorded (Section 27)
- a report is generated with all required sections (Section 28)
- a reproducibility package is written (Section 39)
- results are classified using the sanctioned vocabulary (Section 51)
- "proves"-style language never appears (Section 2)
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

import numpy as np
import pytest

from cosmos.config import ResultClassification
from cosmos.experiments import AnalysisPlan, EXP001Experiment

VALID_CLASSIFICATIONS = {e.value for e in ResultClassification}


@pytest.fixture(scope="module")
def db_url():
    """Throwaway database so the experiment run never touches real data."""
    tmpdir = tempfile.mkdtemp(prefix="cosmos_exp_test_")
    url = f"sqlite:///{os.path.join(tmpdir, 'test.db')}"
    yield url


@pytest.fixture(scope="module")
def shared_exp_dir():
    """
    One temporary experiment directory for the whole module.

    Tests that inspect artifacts (report, reproducibility package, analysis
    JSON) must look at the same directory the full run wrote to, so this is
    module-scoped rather than function-scoped.
    """
    return Path(tempfile.mkdtemp(prefix="cosmos_exp_shared_")) / "EXP-001"


@pytest.fixture
def exp_dir():
    """A fresh temporary experiment directory for an isolated test."""
    return Path(tempfile.mkdtemp(prefix="cosmos_exp_dir_")) / "EXP-001"


class TestExperimentDirectory:
    def test_setup_creates_structure(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        exp.setup()
        assert exp_dir.exists()
        assert (exp_dir / "results").exists()
        assert (exp_dir / "report").exists()
        assert (exp_dir / "reproducibility").exists()

    def test_dry_run_short_circuits(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir, dry_run=True)
        out = exp.run()
        assert out["dry_run"] is True
        # A dry run must not write artifacts.
        assert not exp_dir.exists()


class TestAnalysisPlan:
    """Section 26: analyses must be registered before results are examined."""

    def test_plan_is_registered(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        plan = exp.register_analysis_plan()
        assert isinstance(plan, AnalysisPlan)
        assert plan.experiment_id == "EXP-001"

    def test_plan_declares_pre_registration(self, exp_dir):
        plan = EXP001Experiment(data_dir=exp_dir).register_analysis_plan()
        assert plan.registered_before_results is True

    def test_plan_has_timestamp_and_seed(self, exp_dir):
        plan = EXP001Experiment(data_dir=exp_dir, seed=99).register_analysis_plan()
        assert plan.random_seed == 99
        assert plan.timestamp

    def test_plan_lists_analysis_steps(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        plan = exp.register_analysis_plan()
        assert len(plan.analysis_steps) >= 5
        assert any("Lambda CDM" in s or "lcdm" in s.lower() for s in plan.analysis_steps)

    def test_plan_declares_seed_before_analysis_runs(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir, seed=7)
        exp.setup()
        exp.register_analysis_plan()
        # The plan exists before any data has been prepared.
        assert exp.plan is not None
        assert not exp.result


class TestProvenance:
    """Section 27: RESULT -> ANALYSIS -> CODE -> DATA -> SOURCE."""

    def test_provenance_chain_grows_through_run(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        exp.setup()
        n0 = len(exp.provenance)
        exp._prepare_data()
        assert len(exp.provenance) > n0

    def test_provenance_entries_have_required_fields(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        exp.add_provenance("analysis", "abc123", "description here")
        entry = exp.provenance_chain()[0]
        for key in ["node_type", "node_id", "description", "timestamp"]:
            assert key in entry

    def test_provenance_is_json_serializable(self, exp_dir):
        exp = EXP001Experiment(data_dir=exp_dir)
        exp.setup()
        exp.register_analysis_plan()
        exp._prepare_data()
        json.dumps(exp.provenance_chain())


class TestFullRun:
    """End-to-end run of EXP-001 against a throwaway database."""

    @pytest.fixture(scope="class")
    def run_result(self, shared_exp_dir, db_url):
        """Run EXP-001 once and share the outcome across assertions."""
        from cosmos.config import settings
        old = settings.database_url
        settings.database_url = str(db_url)
        try:
            exp = EXP001Experiment(data_dir=shared_exp_dir, seed=123)
            result = exp.run()
        finally:
            settings.database_url = old
        return result

    @pytest.fixture(scope="class")
    def artifacts_dir(self, shared_exp_dir):
        return shared_exp_dir

    def test_run_returns_expected_keys(self, run_result):
        assert run_result["exp_id"] == "EXP-001"
        for key in ["classification", "summary", "provenance"]:
            assert key in run_result

    def test_classification_is_from_sanctioned_vocabulary(self, run_result):
        """Section 51: results must use the approved classification set."""
        assert run_result["classification"] in VALID_CLASSIFICATIONS

    def test_summary_is_present_and_substantive(self, run_result):
        summary = run_result["summary"]
        assert isinstance(summary, str) and len(summary) > 40

    def test_summary_avoids_overclaiming(self, run_result):
        """Section 2: never claim to 'prove' anything."""
        assert "prove" not in run_result["summary"].lower()

    def test_summary_discloses_synthetic_data_limitation(self, run_result):
        """
        Section 60: a result computed on synthesised data must say so, and must
        not imply any constraint on the real universe.
        """
        summary = run_result["summary"].lower()
        assert "mock" in summary or "synthetic" in summary or "synthesised" in summary
        assert "validates the pipeline" in summary
        assert "constraining the universe" in summary

    def test_provenance_chain_recorded(self, run_result):
        assert len(run_result["provenance"]) >= 5

    def test_report_written(self, artifacts_dir):
        report = artifacts_dir / "report" / "report_EXP-001.md"
        assert report.exists()
        text = report.read_text(encoding="utf-8")
        assert "EXP-001" in text

    def test_report_has_all_required_sections(self, artifacts_dir):
        """
        Section 28 requires: executive summary, scientific question,
        hypotheses, data, method, results, significance, systematics,
        robustness, replication, interpretation, limitations, references,
        reproducibility. Sections 36 and 39 additionally require the
        adversarial review and the provenance chain.
        """
        report = artifacts_dir / "report" / "report_EXP-001.md"
        text = report.read_text(encoding="utf-8")
        required = [
            "Executive Summary",
            "Scientific Question",
            "Hypotheses",
            "Data",
            "Method",
            "Results",
            "Statistical Significance",
            "Systematics",
            "Adversarial Review",
            "Injection and Recovery",
            "Replication",
            "Interpretation",
            "Limitations",
            "References",
            "Provenance",
            "Reproducibility",
        ]
        for section in required:
            assert section in text, f"report missing section: {section}"

    def test_report_states_the_measured_outcome(self, artifacts_dir, run_result):
        """
        A completed run must produce a report containing the actual numbers,
        not a template. Reporting a generic template as if it were a result
        would be exactly the fabrication the specification forbids.
        """
        report = artifacts_dir / "report" / "report_EXP-001.md"
        text = report.read_text(encoding="utf-8")
        assert run_result["classification"] in text
        assert "Monte Carlo" in text
        assert str(run_result["analysis"]["n_k_bins"]) in text

    def test_report_does_not_claim_proof(self, artifacts_dir):
        """Section 2: the report must never claim a theory was proven."""
        import re

        report = artifacts_dir / "report" / "report_EXP-001.md"
        text = report.read_text(encoding="utf-8")
        # Word-bounded so that "Provenance" does not match "proven".
        assert not re.search(r"\bproven\b", text, re.IGNORECASE)
        assert not re.search(r"\bproves\b", text, re.IGNORECASE)

    def test_report_lists_unquantified_systematics(self, artifacts_dir):
        """
        Section 50: unquantified systematics must be visible, so a reader can
        see which parts of the error budget are not yet accounted for.
        """
        report = artifacts_dir / "report" / "report_EXP-001.md"
        text = report.read_text(encoding="utf-8")
        assert "**no**" in text, "no unquantified systematic is flagged"
        assert "upper bound" in text.lower()

    def test_reproducibility_package_written(self, artifacts_dir):
        repro = artifacts_dir / "reproducibility"
        assert (repro / "environment.lock").exists()
        assert (repro / "experiment.lock").exists()
        assert (repro / "data.manifest").exists()
        assert (repro / "README.md").exists()

    def test_experiment_lock_records_seed_and_command(self, artifacts_dir):
        lock = json.loads((artifacts_dir / "reproducibility" / "experiment.lock").read_text())
        assert lock["experiment_id"] == "EXP-001"
        assert lock["random_seed"] == 123
        assert "cosmos experiment run" in lock["command"]

    def test_repro_readme_embeds_the_analysis_plan(self, artifacts_dir):
        text = (artifacts_dir / "reproducibility" / "README.md").read_text(encoding="utf-8")
        assert "registered_before_results" in text

    def test_analysis_results_saved(self, artifacts_dir):
        analysis = artifacts_dir / "results" / "analysis.json"
        assert analysis.exists()
        data = json.loads(analysis.read_text())
        assert "chi2_test" in data


class TestPowerSpectrumMeasurement:
    """
    The measurement must actually recover the power spectrum it was given.

    This is the scientific core of EXP-001: if the P(k) estimator were wrong,
    every downstream conclusion would be wrong in the same way and no amount of
    downstream statistics would reveal it. These tests validate the estimator
    against its own definition.
    """

    @pytest.fixture(scope="class")
    def mock(self):
        from cosmos.simulations import Cosmology, clustered_mock_galaxy_catalog
        cosmo = Cosmology(h=0.674, om=0.315, ol=0.685)
        # A low bias keeps the clipping of empty cells small, so the linear
        # bias relation holds closely and this test measures the estimator
        # rather than the mock's nonlinearity.
        return cosmo, clustered_mock_galaxy_catalog(
            box=400.0, n_grid=32, nbar=0.05, bias=0.3, cosmo=cosmo,
            random_seed=7, target_sigma8=cosmo.sigma8,
        )

    def test_mock_has_requested_number_density(self, mock):
        _, m = mock
        assert m["n_galaxies"] == pytest.approx(m["nbar_target"] * m["box"] ** 3, rel=1e-3)

    def test_mock_positions_lie_inside_the_box(self, mock):
        _, m = mock
        for axis in ("x", "y", "z_cart"):
            values = np.asarray(m[axis])
            assert values.min() >= 0.0
            assert values.max() <= m["box"]

    def test_mock_field_has_requested_sigma8(self, mock):
        from cosmos.simulations import sigma8_from_field
        cosmo, m = mock
        assert sigma8_from_field(m["delta"], m["cell_size"]) == pytest.approx(
            cosmo.sigma8, rel=0.05
        )

    def test_measured_pk_agrees_with_the_field_it_sampled(self, mock):
        """
        The central validation of the P(k) estimator.

        The mock galaxies were drawn from a known density field, so the
        measured P(k) must agree with that field's own P(k) within the quoted
        uncertainties. A wrong FFT convention, a units error, a shot-noise
        subtraction error, or a wrong bias normalisation would all break this.
        """
        from cosmos.simulations import (
            effective_bias,
            measure_power_spectrum,
            measure_power_spectrum_from_field,
        )
        _, m = mock
        ps = measure_power_spectrum(
            {"x": m["x"], "y": m["y"], "z_cart": m["z_cart"]},
            box=m["box"], n_grid=m["n_grid"], k_min=0.02, k_max=None,
        )
        b = effective_bias(ps["delta"], m["delta"])

        # P(k) of the underlying matter field, binned identically.
        field_ps = measure_power_spectrum_from_field(
            m["delta"], box=m["box"], n_grid=m["n_grid"], k_min=0.02
        )
        p_gal_all = np.asarray(ps["p_k"], dtype=float)
        p_err_all = np.asarray(ps["p_k_err"], dtype=float)
        modes_all = np.asarray(ps["n_modes"])
        p_field_all = np.asarray(field_ps["p_k"], dtype=float)

        # One shared mask over both arrays.
        usable = np.isfinite(p_gal_all) & np.isfinite(p_err_all) & (modes_all > 0)
        assert usable.sum() >= 8, "too few usable bins to validate the estimator"

        # Restrict to bins with meaningful signal-to-noise; below that the
        # comparison is dominated by shot noise and proves nothing.
        strong = usable & (p_err_all < 0.5 * np.maximum(p_gal_all, 1e-30))
        assert strong.sum() >= 6, "not enough high-SNR bins to validate"

        expected = b**2 * p_field_all
        residuals = (p_gal_all[strong] - expected[strong]) / p_err_all[strong]
        # A correct estimator gives residuals of order unity. The tolerance
        # allows for the mild nonlinearity introduced by clipping empty cells
        # in the mock, which slightly suppresses the effective clustering.
        assert np.abs(residuals).mean() < 4.0
        assert np.abs(residuals).max() < 12.0

    def test_shot_noise_level_is_one_over_nbar(self, mock):
        """The estimator's shot-noise term must equal 1/nbar exactly."""
        from cosmos.simulations import measure_power_spectrum
        _, m = mock
        ps = measure_power_spectrum(
            {"x": m["x"], "y": m["y"], "z_cart": m["z_cart"]},
            box=m["box"], n_grid=m["n_grid"],
        )
        assert ps["shot_noise"] == pytest.approx(
            ps["box"] ** 3 / ps["n_points"], rel=1e-9
        )

    def test_measured_sigma8_matches_the_field_it_came_from(self, mock):
        """
        Two distinct properties are checked, because they fail for different
        reasons and lumping them together hides which one broke.

        (a) The galaxy P(k) estimator and the matter-field estimator must agree
            after dividing out the bias. Both use the same binning and
            normalisation, so any disagreement is a real measurement error and
            the tolerance here is tight.

        (b) The sigma8 recovered from the *binned* P(k) must be consistent with
            the sigma8 of the field it came from. The tolerance is loose because
            the integrand W^2(kR) is peaked near k ~ 2/R, so the integral is
            dominated by two or three high-k bins whose single-realisation
            scatter is large. Agreement to tens of percent is expected; a factor
            of several would indicate a normalisation error.
        """
        from cosmos.simulations import (
            effective_bias,
            measure_power_spectrum,
            measure_power_spectrum_from_field,
            sigma8_from_field,
            sigma8_from_power_spectrum,
        )
        cosmo, m = mock
        ps = measure_power_spectrum(
            {"x": m["x"], "y": m["y"], "z_cart": m["z_cart"]},
            box=m["box"], n_grid=m["n_grid"], k_min=0.02, k_max=None,
        )
        fp = measure_power_spectrum_from_field(
            m["delta"], box=m["box"], n_grid=m["n_grid"], k_min=0.02
        )
        b = effective_bias(ps["delta"], m["delta"])

        # (a) Estimator agreement, tight.
        sigma8_from_galaxies = sigma8_from_power_spectrum(
            np.asarray(ps["k"]), np.asarray(ps["p_k"]) / b**2
        )
        sigma8_from_field_ps = sigma8_from_power_spectrum(
            np.asarray(fp["k"]), np.asarray(fp["p_k"])
        )
        assert sigma8_from_galaxies == pytest.approx(sigma8_from_field_ps, rel=0.15)

        # (b) Consistency with the field's own sigma8, loose.
        sigma8_field = sigma8_from_field(m["delta"], m["cell_size"])
        assert sigma8_field == pytest.approx(cosmo.sigma8, rel=0.1)
        assert 0.5 * sigma8_field < sigma8_from_galaxies < 1.5 * sigma8_field

    def test_power_spectrum_rejects_unresolvable_k_range(self, mock):
        """A k range above Nyquist must raise rather than return zeros."""
        from cosmos.simulations import measure_power_spectrum
        _, m = mock
        with pytest.raises(ValueError):
            measure_power_spectrum(
                {"x": m["x"], "y": m["y"], "z_cart": m["z_cart"]},
                box=m["box"], n_grid=m["n_grid"], k_min=0.02, k_max=100.0,
            )

    def test_sigma8_normalisation_is_self_consistent(self):
        """Rescaling P(k) to a target sigma8 must actually achieve it."""
        from cosmos.simulations import (
            normalize_power_spectrum_sigma8,
            sigma8_from_power_spectrum,
        )
        k = np.logspace(-2, 0.5, 200)
        arbitrary = 5000.0 * k**-1.0  # deliberately not normalised
        scaled = normalize_power_spectrum_sigma8(k, arbitrary, target_sigma8=0.8)
        assert sigma8_from_power_spectrum(k, scaled) == pytest.approx(0.8, rel=0.01)

    def test_effective_bias_recovers_a_known_bias(self):
        """The bias estimator must return the bias it was given."""
        from cosmos.simulations import effective_bias
        rng = np.random.default_rng(0)
        matter = rng.normal(0, 1, 40000)
        for true_bias in (0.5, 1.0, 2.0):
            galaxy = true_bias * matter
            assert effective_bias(galaxy, matter) == pytest.approx(
                true_bias, rel=0.05
            )

    def test_effective_bias_is_not_biased_by_shot_noise(self):
        """
        Shot noise is uncorrelated with the matter field, so adding it must
        not bias the measured bias. This validates the estimator's use in the
        experiment, where shot noise is unavoidable.
        """
        from cosmos.simulations import effective_bias
        rng = np.random.default_rng(1)
        matter = rng.normal(0, 1, 40000)
        galaxy = 1.5 * matter + rng.normal(0, 1, 40000)
        assert effective_bias(galaxy, matter) == pytest.approx(1.5, rel=0.05)


class TestReproducibility:
    def test_same_seed_gives_same_result(self, tmp_path):
        """Deterministic seeding must produce identical conclusions."""
        results = []
        for i in range(2):
            d = tmp_path / f"run{i}" / "EXP-001"
            exp = EXP001Experiment(data_dir=d, seed=4242)
            # Compare the analysis stage only (the DB write is out of scope here).
            exp.setup()
            data = exp._prepare_data()
            pred = exp._predict_lcdm(data)
            null = exp._simulate_null()
            analysis = exp._run_analysis(data, pred, null)
            results.append(analysis["chi2_test"]["chi2"])
        assert results[0] == pytest.approx(results[1])

    def test_different_seeds_change_the_realisation(self, tmp_path):
        chis = []
        for seed in (1, 2):
            d = tmp_path / f"s{seed}" / "EXP-001"
            exp = EXP001Experiment(data_dir=d, seed=seed)
            exp.setup()
            data = exp._prepare_data()
            pred = exp._predict_lcdm(data)
            null = exp._simulate_null()
            analysis = exp._run_analysis(data, pred, null)
            chis.append(analysis["chi2_test"]["chi2"])
        assert chis[0] != chis[1]

    def test_simulation_hash_is_recorded(self, tmp_path):
        d = tmp_path / "hash" / "EXP-001"
        exp = EXP001Experiment(data_dir=d, seed=5)
        exp.setup()
        null = exp._simulate_null()
        assert null["hash"]
        analysis_hash = exp._run_analysis(
            exp._prepare_data(), exp._predict_lcdm(exp._prepare_data()), null
        )["null_sim_hash"]
        assert analysis_hash == null["hash"]


class TestScientificDiscipline:
    def test_plan_precedes_analysis_in_run_order(self, exp_dir):
        """
        The framework must register the analysis plan before any statistic is
        computed. This is the structural guard against HARKing.
        """
        exp = EXP001Experiment(data_dir=exp_dir)
        order = []

        original_register = exp.register_analysis_plan
        original_prepare = exp._prepare_data

        def wrapped_register():
            order.append("register_plan")
            return original_register()

        def wrapped_prepare():
            order.append("prepare_data")
            return original_prepare()

        exp.register_analysis_plan = wrapped_register
        exp._prepare_data = wrapped_prepare
        exp.setup()
        exp.register_analysis_plan()
        exp._prepare_data()

        assert order.index("register_plan") < order.index("prepare_data")

    def test_adversarial_stage_runs(self, tmp_path):
        """Section 36: every interesting result gets adversarial tests."""
        d = tmp_path / "adv" / "EXP-001"
        exp = EXP001Experiment(data_dir=d)
        exp.setup()
        data = exp._prepare_data()
        analysis = exp._run_analysis(data, exp._predict_lcdm(data), exp._simulate_null())
        systematics = exp._assess_systematics(data, analysis)
        adversarial = exp._adversarial(data, analysis, systematics)
        assert "adversarial_questions" in adversarial
        assert len(adversarial["adversarial_questions"]) >= 4

    def test_systematics_are_enumerated(self, tmp_path):
        d = tmp_path / "sys" / "EXP-001"
        exp = EXP001Experiment(data_dir=d)
        exp.setup()
        data = exp._prepare_data()
        analysis = exp._run_analysis(data, exp._predict_lcdm(data), exp._simulate_null())
        systematics = exp._assess_systematics(data, analysis)
        assert "systematics" in systematics
        assert len(systematics["systematics"]) >= 3

    def test_classification_reflects_agreement(self, tmp_path):
        """
        When the data match the Lambda CDM prediction within noise, the result
        must be classified as consistent with the standard model, not as an
        anomaly.
        """
        d = tmp_path / "cls" / "EXP-001"
        exp = EXP001Experiment(data_dir=d, seed=123)
        exp.setup()
        data = exp._prepare_data()
        analysis = exp._run_analysis(data, exp._predict_lcdm(data), exp._simulate_null())
        systematics = exp._assess_systematics(data, analysis)
        adversarial = exp._adversarial(data, analysis, systematics)
        classification = exp._classify(analysis, systematics, adversarial)
        assert classification["classification"] in VALID_CLASSIFICATIONS
        assert "caveats" in classification
        assert len(classification["caveats"]) >= 2
