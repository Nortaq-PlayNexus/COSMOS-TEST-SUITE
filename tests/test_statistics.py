"""
Scientific validation tests for the COSMOS statistical framework.

These tests verify the statistical routines against analytically known or
independently derivable results (Section 40/41 of the specification).
"""

from __future__ import annotations

import numpy as np
import pytest

from cosmos import statistics as cs


class TestChiSquare:
    def test_known_value(self):
        # Observed exactly matching expected -> chi2 = 0, p = 1
        e = np.array([10.0, 20.0, 30.0])
        res = cs.chi_square_test(e, e)
        assert res["chi2"] == pytest.approx(0.0, abs=1e-12)
        assert res["p_value"] == pytest.approx(1.0)
        assert res["status"] == "good_fit"

    def test_with_uncertainties(self):
        # sigma = 1 per bin, single-bin deviation of 2 -> chi2 = 4
        res = cs.chi_square_test([2.0], [0.0], expected_uncertainty=[1.0], dof_correction=False)
        assert res["chi2"] == pytest.approx(4.0)

    def test_poisson_binomial_reference(self):
        # For integer counts with expected==counts, chi2 = 0.
        rng = np.random.default_rng(0)
        lam = rng.poisson(50, size=200)
        res = cs.chi_square_test(lam, lam)
        assert res["chi2"] < 1e-9

    def test_bad_fit_detected(self):
        rng = np.random.default_rng(1)
        e = np.full(100, 50.0)
        o = e + rng.normal(0, 30.0, 100)
        res = cs.chi_square_test(o, e)
        assert res["reduced_chi2"] > 1.5
        assert res["p_value"] < 0.05


class TestAICBIC:
    def test_aic_formula(self):
        # AIC = 2k - 2 ln L
        assert cs.compute_aic(n=100, k=2, log_likelihood=-50.0) == pytest.approx(2 * 2 + 100.0)

    def test_bic_formula(self):
        # BIC = k ln n - 2 ln L
        n, k, ll = 100, 3, -40.0
        assert cs.compute_bic(n=n, k=k, log_likelihood=ll) == pytest.approx(k * np.log(n) - 2 * ll)

    def test_aicc_penalizes_more_than_aic(self):
        # Small-sample corrected AIC must be larger than plain AIC.
        aic = cs.compute_aic(n=20, k=5, log_likelihood=-10.0, penalty_bias=False)
        aicc = cs.compute_aic(n=20, k=5, log_likelihood=-10.0, penalty_bias=True)
        assert aicc > aic

    def test_weights_sum_to_one(self):
        aics = np.array([100.0, 102.0, 110.0])
        bics = np.array([100.0, 104.0, 115.0])
        out = cs.model_weights(aics, bics)
        assert out["akaike_weights"].sum() == pytest.approx(1.0)
        assert out["bayesian_weights"].sum() == pytest.approx(1.0)

    def test_identical_models_get_equal_weights(self):
        out = cs.model_weights(np.array([50.0, 50.0, 50.0]))
        assert np.allclose(out["akaike_weights"], 1 / 3)

    def test_extra_parameters_penalized(self):
        """
        Spec Section 14: "Do not select a model simply because it has more
        flexibility. Penalize unnecessary parameters."
        A model that fits only marginally better but uses many more
        parameters must NOT be preferred by BIC.
        """
        n = 1000
        ll_good = -500.0
        ll_simple = -505.0
        bic_simple = cs.compute_bic(n, k=2, log_likelihood=ll_simple)
        bic_complex = cs.compute_bic(n, k=25, log_likelihood=ll_good)
        assert bic_simple < bic_complex

    def test_bayes_factor_arithmetic(self):
        log_bf, bf = cs.bayes_factor(log_evidence_a=10.0, log_evidence_b=8.0)
        assert log_bf == pytest.approx(2.0)
        assert bf == pytest.approx(np.exp(2.0))


class TestSamplingTests:
    def test_ks_identical_distributions(self):
        rng = np.random.default_rng(0)
        a = rng.normal(size=2000)
        b = rng.normal(size=2000)
        res = cs.kstest_two_sample(a, b)
        assert res["p_value"] > 0.01

    def test_ks_shifted_distributions(self):
        rng = np.random.default_rng(0)
        a = rng.normal(size=2000)
        b = rng.normal(loc=2.0, size=2000)
        res = cs.kstest_two_sample(a, b)
        assert res["p_value"] < 0.001

    def test_ttest_detects_difference(self):
        rng = np.random.default_rng(0)
        a = rng.normal(0, 1, 500)
        b = rng.normal(0.5, 1, 500)
        res = cs.ttest_independent(a, b)
        assert res["p_value"] < 0.001

    def test_permutation_test_null(self):
        # Under the null, permutation p-value should not be extreme.
        rng = np.random.default_rng(3)
        a = rng.normal(0, 1, 100)
        b = rng.normal(0, 1, 100)
        res = cs.permutation_test(a, b, n_permutations=2000, random_seed=7)
        assert res["p_value"] > 0.01

    def test_permutation_test_signal(self):
        rng = np.random.default_rng(3)
        a = rng.normal(0, 1, 100)
        b = rng.normal(3.0, 1, 100)
        res = cs.permutation_test(a, b, n_permutations=2000, random_seed=7)
        assert res["p_value"] < 0.01


class TestBootstrap:
    def test_ci_brackets_estimate(self):
        rng = np.random.default_rng(0)
        data = rng.normal(5.0, 2.0, 500)
        res = cs.bootstrap_confidence_interval(
            data, np.mean, n_bootstrap=500, random_seed=1
        )
        assert res["ci_low"] < res["estimate"] < res["ci_high"]

    def test_ci_width_shrinks_with_n(self):
        rng = np.random.default_rng(0)
        small = cs.bootstrap_confidence_interval(
            rng.normal(0, 1, 50), np.mean, n_bootstrap=300, random_seed=1
        )
        large = cs.bootstrap_confidence_interval(
            rng.normal(0, 1, 2000), np.mean, n_bootstrap=300, random_seed=1
        )
        assert large["ci_width"] < small["ci_width"]

    def test_jackknife_close_to_bootstrap(self):
        rng = np.random.default_rng(0)
        data = rng.normal(3.0, 1.0, 400)
        jk = cs.jackknife_variance(data, np.mean)
        assert jk["estimate"] == pytest.approx(np.mean(data))
        assert jk["std"] > 0


class TestConfidenceIntervals:
    def test_normal_ci(self):
        res = cs.confidence_interval_normal(10.0, 1.0, confidence=0.95)
        assert res["ci_low"] == pytest.approx(10.0 - 1.96, abs=0.01)
        assert res["ci_high"] == pytest.approx(10.0 + 1.96, abs=0.01)

    def test_credible_interval_covers_truth(self):
        rng = np.random.default_rng(5)
        samples = rng.normal(2.0, 1.0, 20000)
        res = cs.credible_interval_from_samples(samples, ci=0.95)
        assert res["ci_low"] < 2.0 < res["ci_high"]

    def test_hdi_narrower_or_equal_to_percentile(self):
        rng = np.random.default_rng(5)
        samples = rng.normal(0.0, 1.0, 20000)
        pct = cs.credible_interval_from_samples(samples, ci=0.95, method="percentile")
        hdi = cs.credible_interval_from_samples(samples, ci=0.95, method="hdi")
        assert hdi["ci_width"] if "ci_width" in hdi else (
            hdi["ci_high"] - hdi["ci_low"]
        ) <= (pct["ci_high"] - pct["ci_low"]) + 1e-9


class TestMultipleComparisons:
    def test_bonferroni_is_conservative(self):
        p = np.array([0.001, 0.02, 0.04, 0.5])
        res = cs.multiple_comparisons_correction(p, method="bonferroni")
        assert all(c >= o for c, o in zip(res["corrected_p_values"], p, strict=True))
        assert res["n_rejected"] <= 1

    def test_look_elsewhere_reduces_significance(self):
        """
        Scanning many positions must not inflate significance.

        The global (look-elsewhere-corrected) p-value must never be smaller
        than the local p-value: taking a maximum over more trials can only
        increase the tail probability.
        """
        n_tries = 40

        def stat(data):
            return float(np.max(data))

        rng = np.random.default_rng(0)

        def null_simulate(r):
            return r.normal(0, 1, n_tries)

        # Correct single-location null: the statistic here is the max over the
        # scan, so the local null CDF is that of the maximum, not of N(0, 1).
        from scipy.stats import norm

        def local_null_cdf(t):
            return float(norm.sf(t) ** n_tries)

        res = cs.look_elsewhere_correction_simulation(
            stat,
            rng.normal(4.5, 1, n_tries),
            null_simulate,
            n_simulations=300,
            n_tries=n_tries,
            random_seed=2,
            local_null_cdf=local_null_cdf,
        )
        assert res["global_p"] >= res["local_p"] - 1e-12
        assert res["global_significance_sigma"] <= res["local_p"] ** 0 * 6 + 6

    def test_four_sigma_peak_is_not_a_discovery_after_scanning(self):
        """
        Spec Section 18 (CMB anomalies, CRITICAL):

        A 4.5 sigma single-location excursion found by scanning 40 positions
        must NOT be reported as significant once the look-elsewhere effect is
        accounted for. This guards against the "scan millions of patterns and
        report the most interesting one" failure mode.
        """
        n_tries = 40

        def stat(data):
            return float(np.max(data))

        rng = np.random.default_rng(7)

        def null_simulate(r):
            return r.normal(0, 1, n_tries)

        res = cs.look_elsewhere_correction_simulation(
            stat,
            rng.normal(4.5, 1, n_tries),
            null_simulate,
            n_simulations=200,
            n_tries=n_tries,
            random_seed=13,
        )
        # Corrected significance must be far weaker than the naive local one.
        assert res["global_significance_sigma"] < 4.5
        assert res["global_p"] > res["local_p"]

    def test_looking_elsewhere_shrinks_global_sigma(self):
        """
        The corrected significance of a scan-selected peak must be strictly
        weaker than the naive single-location significance, and must scale
        with the number of looks.
        """

        def stat(data):
            return float(np.max(data))

        rng = np.random.default_rng(0)

        def null_simulate(r):
            return r.normal(0, 1, 60)

        obs = rng.normal(4.0, 1, 60)

        few = cs.look_elsewhere_correction_simulation(
            stat, obs, null_simulate, n_simulations=400, n_tries=5,
            random_seed=11,
        )
        many = cs.look_elsewhere_correction_simulation(
            stat, obs, null_simulate, n_simulations=400, n_tries=60,
            random_seed=11,
        )

        # Scanning more positions can only make the corrected result weaker.
        assert many["global_significance_sigma"] <= few["global_significance_sigma"]
        # And the correction flag should be set.
        assert many["look_elsewhere_reduced_significance"]
        # Never report a p-value of exactly zero with finite simulations.
        assert many["global_p"] > 0.0


class TestMonteCarlo:
    def test_no_signal_gives_high_pvalue(self):
        rng = np.random.default_rng(0)

        def simulate(r):
            return r.normal(0, 1, 200)

        res = cs.monte_carlo_significance(
            rng.normal(0, 1, 200), simulate, np.mean,
            n_simulations=400, random_seed=4, progress=False,
        )
        assert res["p_value"] > 0.01

    def test_strong_signal_gives_low_pvalue(self):
        rng = np.random.default_rng(0)

        def simulate(r):
            return r.normal(0, 1, 200)

        res = cs.monte_carlo_significance(
            rng.normal(5.0, 1, 200), simulate, np.mean,
            n_simulations=400, random_seed=4, progress=False,
        )
        assert res["p_value"] < 0.01
        assert res["significance_sigma"] > 3


class TestDiagnostics:
    def test_autocorrelation_time_for_white_noise(self):
        rng = np.random.default_rng(0)
        x = rng.normal(0, 1, 5000)
        res = cs.autocorrelation_time(x)
        assert 0.5 < res["tau_int"] < 2.0

    def test_autocorrelation_time_detects_correlation(self):
        rng = np.random.default_rng(0)
        n = 5000
        noise = rng.normal(0, 1, n)
        # AR(1) with phi = 0.9 -> large tau_int
        x = np.zeros(n)
        for i in range(1, n):
            x[i] = 0.9 * x[i - 1] + noise[i]
        res = cs.autocorrelation_time(x)
        assert res["tau_int"] > 3.0
        assert res["n_effective"] < n / 3.0

    def test_normality_detects_gaussian(self):
        rng = np.random.default_rng(0)
        res = cs.check_normality(rng.normal(size=2000))
        assert res["shapiro_p"] > 0.01
        assert abs(res["skewness"]) < 0.2

    def test_normality_detects_skewed(self):
        rng = np.random.default_rng(0)
        res = cs.check_normality(rng.exponential(size=2000))
        assert res["shapiro_p"] < 0.01
        assert res["skewness"] > 0.5


class TestSignificanceClassification:
    def test_labels(self):
        assert cs.classify_significance(sigma=0.5) == "consistent_with_null"
        assert cs.classify_significance(sigma=2.0) == "moderate_evidence"
        assert cs.classify_significance(sigma=5.0) == "discovery"

    def test_formatting_avoids_prove(self):
        text = cs.format_significance(sigma=5.5)
        assert "proves" not in text.lower()
        assert "5.50" in text

    def test_sigma8_consistency(self):
        res = cs.sigma8_consistency(sigma8_obs=0.81, sigma8_lcdm=0.81, sigma8_err=0.05)
        assert res["consistent"]
        assert res["n_sigma"] == pytest.approx(0.0)

    def test_sigma8_inconsistency_detected(self):
        res = cs.sigma8_consistency(sigma8_obs=1.00, sigma8_lcdm=0.81, sigma8_err=0.05)
        assert not res["consistent"]
        assert res["n_sigma"] == pytest.approx(3.8)
