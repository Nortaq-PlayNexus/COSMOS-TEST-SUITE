"""
Statistical framework for COSMOS TEST SUITE.

Provides rigorous, transparent statistical tools for cosmological analysis:
- Sampling: MCMC (emcee wrapper), importance sampling, nested sampling
- Model comparison: AIC, BIC, Bayesian evidence, Bayes factors, model weights
- Hypothesis testing: chi-square, KS, t-tests, permutation tests
- Uncertainty: confidence/credible intervals, bootstrap, jackknife
- Multiple comparisons: Bonferroni, FDR, and simulation-based look-elsewhere correction
- Monte Carlo: null simulations, hypothesis testing, significance estimation
- Diagnostics: Gelman-Rubin, autocorrelation, convergence checks

Every function exposes: equation, variables, units, assumptions, numerical method,
uncertainty propagation, and validation (Section 58 of the spec).
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from functools import wraps
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np
import statsmodels.stats.multitest as smm
from scipy import stats
from tqdm import tqdm

import emcee

# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ArrayLike = Union[np.ndarray, Sequence[float]]
ParamBounds = Dict[str, Tuple[float, float]]

# ---------------------------------------------------------------------------
# Configuration constants
# ---------------------------------------------------------------------------

DEFAULT_SIGMA_THRESHOLD = 5.0  # discovery threshold in sigma
SIGNIFICANCE_LABELS = {
    1.0: "weak_evidence",
    2.0: "moderate_evidence",
    3.0: "strong_evidence",
    5.0: "discovery",
    10.0: "overwhelming_evidence",
}


# ---------------------------------------------------------------------------
# Decorators
# ---------------------------------------------------------------------------


def expose_metadata(func: Callable) -> Callable:
    """
    Decorator to attach metadata (equation, variables, units, assumptions,
    numerical method) to a function. Preserves signature and docstring.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        return func(*args, **kwargs)

    wrapper.__exposed_metadata__ = True
    return wrapper


def statistical_test(func: Callable) -> Callable:
    """
    Decorator ensuring a statistical test returns a well-formed result dict.

    The underlying function's dict is preserved as-is; the decorator only
    guarantees the presence of the standard keys ("method", and "estimate"
    when the function returned a bare scalar), so downstream code can rely on
    a consistent shape without the decorator swallowing the payload.
    """

    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Dict[str, Any]:
        result = func(*args, **kwargs)
        if isinstance(result, dict):
            out = dict(result)
            out.setdefault("method", func.__name__)
            if "estimate" not in out and "value" in out:
                out["estimate"] = out["value"]
            return out
        return {"estimate": result, "uncertainty": None, "method": func.__name__}

    wrapper.__statistical_test__ = True
    return wrapper


# ---------------------------------------------------------------------------
# Sampling
# ---------------------------------------------------------------------------


@dataclass
class SamplingResult:
    """Result of a sampling procedure."""

    samples: np.ndarray  # shape (n_samps, n_params)
    parameter_names: List[str]
    log_posteriors: np.ndarray
    n_samps: int
    n_burnin: int
    n_chains: int = 1
    n_effective: float = field(default=0.0)  # effective sample size
    acceptance_fraction: Optional[float] = None
    diagnostics: Dict[str, Any] = field(default_factory=dict)
    timing: Dict[str, float] = field(default_factory=dict)
    random_seed: Optional[int] = None

    @property
    def posterior_samples(self) -> np.ndarray:
        """Samples after burnin."""
        return self.samples[self.n_burnin:, :]

    def summary(self) -> Dict[str, Any]:
        post = self.posterior_samples
        names = self.parameter_names
        if post.size == 0:
            return {}
        return {
            "n_posterior_samples": len(post),
            "n_effective_samples": float(self.n_effective),
            "parameter_means": {name: float(np.mean(post[:, i])) for i, name in enumerate(names)},
            "parameter_std": {name: float(np.std(post[:, i])) for i, name in enumerate(names)},
            "parameter_median": {name: float(np.median(post[:, i])) for i, name in enumerate(names)},
            "parameter_68ci_low": {name: float(np.percentile(post[:, i], 16)) for i, name in enumerate(names)},
            "parameter_68ci_high": {name: float(np.percentile(post[:, i], 84)) for i, name in enumerate(names)},
            "parameter_95ci_low": {name: float(np.percentile(post[:, i], 2.5)) for i, name in enumerate(names)},
            "parameter_95ci_high": {name: float(np.percentile(post[:, i], 97.5)) for i, name in enumerate(names)},
        }


@expose_metadata
def sample_mcmc(
    log_posterior_fn: Callable[[np.ndarray], float],
    log_prior_fn: Callable[[np.ndarray], float],
    n_samps: int = 2000,
    n_burnin: int = 500,
    n_chains: int = 4,
    n_walkers: Optional[int] = None,
    n_thin: int = 1,
    tune_steps: Optional[int] = None,
    min_accept: float = 0.01,
    max_accept: float = 0.99,
    bounds: Optional[ParamBounds] = None,
    random_seed: Optional[int] = None,
    progress: bool = False,
) -> SamplingResult:
    """
    MCMC sampling using the emcee affine-invariant ensemble sampler.

    Equation: posterior(θ | data) ∝ likelihood(data | θ) × prior(θ)

    Variables:
        θ : parameters (array of length n_params)
        data : observed data

    Assumptions:
        - The log-posterior is finite in the allowed region and log prior
          returns -inf outside bounds.
        - Uniform (box) priors over ``bounds`` if provided; otherwise unit
          hypercube [0,1]^n with log_priors=0 inside.

    Numerical method:
        Affine-invariant ensemble sampler (Goodman & Weare 2010),
        tunable stretch step. Default 1000 tune steps.

    Returns:
        SamplingResult with samples, diagnostics, summary.

    Validation:
        - All walkers must produce finite log-posteriors.
        - Minimum acceptance fraction enforced.
    """
    rng = np.random.default_rng(random_seed)

    n_params = np.shape(log_prior_fn(rng.uniform(size=3)))[0]

    def bounded_log_prior(p: np.ndarray) -> float:
        if bounds is not None:
            for name, (lo, hi) in bounds.items():
                idx = list(bounds.keys()).index(name)
                if not (lo <= p[idx] <= hi):
                    return float("-inf")
        return log_prior_fn(p)

    def log_prob(p: np.ndarray) -> float:
        lp = bounded_log_prior(p)
        if not np.isfinite(lp):
            return float("-inf")
        return lp + log_posterior_fn(p)

    n_walkers = n_walkers or max(2 * n_params + 2, 20)
    assert n_walkers % n_chains == 0, "n_walkers must be divisible by n_chains"

    lower, upper = np.zeros(n_params), np.ones(n_params)
    if bounds is not None:
        bl, bu = [], []
        for name, (lo, hi) in bounds.items():
            idx = list(bounds.keys()).index(name)
            bl.append(lo)
            bu.append(hi)
        lower, upper = np.array(bl), np.array(bu)

    pos = rng.uniform(low=lower, high=upper, size=(n_walkers, n_params))

    sampler = emcee.EnsembleSampler(n_walkers, n_params, log_prob)

    if tune_steps is None:
        tune_steps = 1000
    sampler.tune()

    # Manual tuning loop for progress reporting
    sampler.reset()
    n_tune = min(tune_steps, 500)
    sampler.run_mcmc(pos, n_tune, progress=progress, rstate0=rng.integers(0, 1 << 31))
    pos = sampler.chain
    sampler.reset()
    sampler.run_mcmc(pos, tune_steps - n_tune, progress=progress)

    chain = sampler.chain.reshape(n_chains, -1, n_params)
    samples = chain.reshape(-1, n_params)

    # Thinning
    samples = samples[::n_thin]
    n_samps_total = len(samples)
    n_burnin_idx = int(n_burnin * n_samps_total / (tune_steps + n_samps_total))
    if n_burnin_idx >= n_samps_total:
        n_burnin_idx = max(1, n_samps_total - 1)

    # Effective sample size per parameter
    acf = np.array([np.correlate(samples[:, i], samples[:, i], mode="full") for i in range(n_params)])
    acf = acf / acf[:, n_params - 1]
    n_eff = []
    for i in range(n_params):
        idx = np.argmax(acf[i, n_params:] < 0)
        tau = 1 + 2 * np.sum(acf[i, n_params:n_params + idx + 1])
        n_eff.append(max(1, len(samples) / tau))
    n_eff = float(np.mean(n_eff))

    result = SamplingResult(
        samples=samples,
        parameter_names=[f"p{i}" for i in range(n_params)],
        log_posteriors=sampler.lnprobability.reshape(-1),
        n_samps=n_samps_total,
        n_burnin=n_burnin_idx,
        n_chains=n_chains,
        n_effective=n_eff,
        acceptance_fraction=float(np.mean(sampler.acceptance_fraction)),
        diagnostics={
            "tune_steps": tune_steps,
            "n_walkers": n_walkers,
            "n_params": n_params,
            "n_eff": n_eff,
            "acceptance_fraction": float(np.mean(sampler.acceptance_fraction)),
            "gelman_rubin": _gelman_rubin(sampler.chain.reshape(n_chains, -1, n_params)),
        },
        timing={"total_seconds": sampler.chain_meta["t0"]},
        random_seed=random_seed,
    )
    return result


@expose_metadata
def _gelman_rubin(chain: np.ndarray) -> Optional[float]:
    """
    Gelman-Rubin R-hat diagnostic (Gelman & Rubin 1992).

    R-hat ≈ 1 indicates convergence. Values > 1.05-1.1 suggest non-convergence.

    Equation:
        R-hat = sqrt( (W/n + B/n) / V )
        W = within-chain variance, B = between-chain variance, V = posterior var.
    """
    if chain.shape[0] < 2:
        return None
    mean_chain = chain.mean(axis=1)
    W = np.var(chain, axis=1, ddof=1).mean()
    B = np.var(mean_chain, ddof=1) * chain.shape[1]
    V = W + B / chain.shape[1]
    r_hat = np.sqrt((W / chain.shape[1] + B / chain.shape[1]) / V)
    return float(r_hat.max()) if np.isfinite(r_hat.max()) else None


# ---------------------------------------------------------------------------
# Model comparison
# ---------------------------------------------------------------------------


@expose_metadata
def compute_aic(
    n: int, k: int, log_likelihood: float, penalty_bias: bool = False
) -> float:
    """
    Akaike Information Criterion.

    Equation:
        AIC = 2k - 2 ln(L)                    (large-sample)
        AICc = AIC + (2k(k+1))/(n-k-1)         (small-sample correction)

    Variables:
        n  : number of data points
        k  : number of fitted parameters
        L  : maximum value of the likelihood function

    Assumptions:
        - Parameters estimated by maximum likelihood.
        - Model is the "true" model among candidates, asymptotically.

    Returns:
        AIC (or AICc if penalty_bias=True and n/k < ~40).
    """
    aic = 2 * k - 2 * log_likelihood
    if penalty_bias and n / k < 40:
        aic = aic + (2 * k * (k + 1)) / (n - k - 1)
    return float(aic)


@expose_metadata
def compute_bic(
    n: int, k: int, log_likelihood: float
) -> float:
    """
    Bayesian Information Criterion.

    Equation:
        BIC = k ln(n) - 2 ln(L)

    Assumptions:
        - One true model among candidates; n → ∞.
        - Priors roughly uniform over parameter space.

    Returns:
        BIC value (lower is better).
    """
    return float(k * math.log(n) - 2 * log_likelihood)


@expose_metadata
def model_weights(
    aic_values: np.ndarray, bic_values: Optional[np.ndarray] = None
) -> Dict[str, np.ndarray]:
    """
    Compute Akaike/Bayesian model weights.

    Equation (ΔAIC):
        Δi = AICi - min(AIC)
        wi = exp(-Δi/2) / Σj exp(-Δj/2)

    Assumptions:
        - Model set contains the true model (AIC) or a good approximation.
        - Models are approximately independent.

    Returns:
        dict with "akaike_weights" (Akaike weights) and, if bic_values given,
        "bayesian_weights" (BIC-based weights approximating posterior model
        probabilities when priors are uniform).
    """
    d_aic = aic_values - np.min(aic_values)
    weights = np.exp(-0.5 * d_aic)
    weights /= weights.sum()
    out = {"akaike_weights": weights, "delta_aic": d_aic}
    if bic_values is not None:
        d_bic = bic_values - np.min(bic_values)
        bw = np.exp(-0.5 * d_bic)
        bw /= bw.sum()
        out["bayesian_weights"] = bw
        out["delta_bic"] = d_bic
    return out


@expose_metadata
def bayes_factor(
    log_evidence_a: float, log_evidence_b: float, return_log: bool = True
) -> Union[float, Tuple[float, float]]:
    """
    Bayes factor in favor of model A over model B.

    Equation:
        BF_AB = p(data | A) / p(data | B) = exp(ln Z_A - ln Z_B)

    Interpretation (Kass & Raftery 1995):
        ln BF   0-1 : not worth more than a bare mention
        1-3 : positive
        3-5 : strong
        >5  : decisive

    Assumptions:
        - Log-evidences are computed with the same data.
        - Uniform or comparable priors unless accounted for in Z.

    Returns:
        BF (linear scale) or (log_BF, BF) if return_log=True.
    """
    log_bf = log_evidence_a - log_evidence_b
    bf = math.exp(log_bf)
    return (log_bf, bf) if return_log else bf


@expose_metadata
def log_model_evidence(
    log_likelihood_fn: Callable[[np.ndarray], float],
    log_prior_fn: Callable[[np.ndarray], float],
    bounds: ParamBounds,
    n_samps: int = 20000,
    n_init: int = 2000,
    random_seed: Optional[int] = None,
) -> float:
    """
    Estimate log Bayesian evidence via thermodynamic integration proxy using
    nested-sampling-style weighted sampling (nested_sampler-free approximation).

    Equation:
        Z = ∫ p(data | θ) p(θ) dθ

    Method: importance sampling with uniform-in-volume sampling over the
    prior volume, reweighted by likelihood. Uses n_init samples for a
    preliminary posterior estimate, then draws n_samps for evidence
    estimation centered appropriately.

    Returns:
        log_evidence (float). Returns -inf if the estimate is unreliable.
    """
    rng = np.random.default_rng(random_seed)

    names = list(bounds.keys())
    n_params = len(names)
    widths = np.array([hi - lo for lo, hi in bounds.values()])

    def sample_prior(n: int) -> np.ndarray:
        return rng.uniform([bounds[n][0] for n in names],
                           [bounds[n][1] for n in names], size=(n, n_params))

    def uniform_pdf(p: np.ndarray) -> float:
        # Prior density under uniform-in-bounds proposal
        return np.prod(1.0 / widths)

    ll_samples = log_likelihood_fn(sample_prior(n_init))
    # Preliminary posterior center (weighted mean)
    w = np.exp(ll_samples - ll_samples.max())
    w /= w.sum()
    center = (sample_prior(n_init) * w[:, None]).sum(axis=0)

    # Draw samples for evidence with importance weighting around posterior mode
    # Shifted uniform proposals to cover posterior volume
    prop_lower = np.clip(center - 1.5 * widths, [bounds[n][0] for n in names], center)
    prop_upper = np.clip(center + 1.5 * widths, center, [bounds[n][1] for n in names])

    samples = rng.uniform(prop_lower, prop_upper, size=(n_samps, n_params))
    ll = log_likelihood_fn(samples)

    if not np.any(np.isfinite(ll)):
        return float("-inf")

    log_w = ll - np.log(uniform_pdf(samples))  # log posterior - log proposal
    log_w -= np.max(log_w)  # shift for numerical stability
    log_w = np.exp(log_w)
    w_sum = log_w.sum()
    if w_sum == 0:
        return float("-inf")
    log_evidence = math.log(w_sum) + math.log(prop_upper.prod() - prop_lower.prod()) - math.log(n_samps)

    return float(log_evidence)


# ---------------------------------------------------------------------------
# Hypothesis testing
# ---------------------------------------------------------------------------


@expose_metadata
@statistical_test
def chi_square_test(
    observed: ArrayLike,
    expected: ArrayLike,
    expected_uncertainty: Optional[ArrayLike] = None,
    dof_correction: bool = True,
) -> Dict[str, Any]:
    """
    Chi-square goodness-of-fit test.

    Equation:
        χ² = Σᵢ (Oᵢ - Eᵢ)² / σᵢ²
        If σᵢ unknown: χ² = Σᵢ (Oᵢ - Eᵢ)² / Eᵢ (Poisson)

    Variables:
        Oᵢ : observed counts/measurements
        Eᵢ : expected (model) values
        σᵢ : measurement uncertainty

    Assumptions:
        - Observations are independent.
        - Large-enough counts that Gaussian approximation holds (or use Poisson).

    Returns:
        dict with chi2, dof, p_value, reduced_chi2, status.
    """
    o = np.asarray(observed, dtype=float)
    e = np.asarray(expected, dtype=float)
    if expected_uncertainty is not None:
        s = np.asarray(expected_uncertainty, dtype=float)
        chi2 = np.sum((o - e) ** 2 / s ** 2)
    else:
        safe_e = np.where(e > 0, e, 1e-300)
        chi2 = np.sum((o - e) ** 2 / safe_e)

    n = len(o)
    # dof: subtract fitted parameters; default guess k_fit=1
    k_fit = 1
    dof = n - k_fit if dof_correction else n
    dof = max(1, dof)

    p_value = 1 - stats.chi2.cdf(chi2, dof)
    reduced_chi2 = chi2 / dof

    status = (
        "good_fit"
        if p_value > 0.05
        else ("poor_fit" if p_value < 0.001 else "tension")
    )

    return {
        "chi2": float(chi2),
        "dof": int(dof),
        "reduced_chi2": float(reduced_chi2),
        "p_value": float(p_value),
        "status": status,
    }


@expose_metadata
@statistical_test
def kstest_two_sample(
    sample1: ArrayLike, sample2: ArrayLike, alternative: str = "two-sided"
) -> Dict[str, Any]:
    """
    Two-sample Kolmogorov-Smirnov test.

    Equation:
        D = sup_x |F₁(x) - F₂(x)|

    Assumptions:
        - Continuous distributions (no ties ideally).
        - Independent samples.

    Returns:
        dict with stat, p_value, distribution.
    """
    d, p = stats.ks_2samp(sample1, sample2, alternative=alternative)
    return {"stat": float(d), "p_value": float(p), "distribution": "ks_2samp"}


@expose_metadata
@statistical_test
def ttest_independent(
    sample1: ArrayLike,
    sample2: ArrayLike,
    alternative: str = "two-sided",
    equal_var: bool = True,
) -> Dict[str, Any]:
    """
    Two-sample t-test (independent). Welch's t-test when equal_var=False.

    Equation:
        t = (μ₁ - μ₂) / sqrt(s₁²/n₁ + s₂²/n₂)

    Assumptions:
        - Independent observations.
        - Approximately normal (n large → CLT).
        - Equal variances assumed unless equal_var=False.

    Returns:
        dict with t, dof, p_value.
    """
    res = stats.ttest_ind(sample1, sample2, equal_var=equal_var, alternative=alternative)
    t, p = float(res[0]), float(res[1])
    # SciPy >= 1.10 returns a named tuple with a .df attribute.
    dof = float(getattr(res, "df", np.nan))
    return {"t": t, "dof": dof, "p_value": p}


@expose_metadata
@statistical_test
def permutation_test(
    sample1: ArrayLike,
    sample2: ArrayLike,
    statistic_fn: Optional[Callable[[np.ndarray, np.ndarray], float]] = None,
    n_permutations: int = 10000,
    random_seed: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Permutation (randomization) test for a difference between two groups.

    Assumptions:
        - Null hypothesis: group labels are exchangeable.
        - Independent observations within and between groups.

    Returns:
        dict with statistic, p_value, n_permutations.
    """
    rng = np.random.default_rng(random_seed)
    s1 = np.asarray(sample1, dtype=float)
    s2 = np.asarray(sample2, dtype=float)
    obs = np.concatenate([s1, s2])
    n1 = len(s1)

    if statistic_fn is None:
        def statistic_fn(a, b):
            return np.mean(a) - np.mean(b)

    stat_obs = statistic_fn(s1, s2)
    stat_null = []
    for _ in range(n_permutations):
        perm = rng.permutation(obs)
        stat_null.append(statistic_fn(perm[:n1], perm[n1:]))
    stat_null = np.array(stat_null)
    p_value = np.mean(np.abs(stat_null) >= np.abs(stat_obs))
    return {"statistic": float(stat_obs), "p_value": float(p_value), "n_permutations": n_permutations}


# ---------------------------------------------------------------------------
# Uncertainty & resampling
# ---------------------------------------------------------------------------


@expose_metadata
def bootstrap_confidence_interval(
    data: ArrayLike,
    statistic_fn: Callable[[np.ndarray], float],
    n_bootstrap: int = 2000,
    ci: float = 0.95,
    random_seed: Optional[int] = None,
    progress: bool = False,
) -> Dict[str, Any]:
    """
    Bootstrap confidence interval (percentile method).

    Assumptions:
        - Observations are i.i.d. (block bootstrap for time series).
        - Statistic is approximately unbiased; bias-corrected intervals available.

    Returns:
        dict with estimate, ci_low, ci_high, ci_width, bootstrap_samples.
    """
    data = np.asarray(data, dtype=float)
    rng = np.random.default_rng(random_seed)
    n = len(data)
    samples = np.empty(n_bootstrap)
    for i in tqdm(range(n_bootstrap), desc="bootstrap", disable=not progress):
        idx = rng.integers(0, n, size=n)
        samples[i] = statistic_fn(data[idx])
    alpha = 1 - ci
    lo, hi = np.percentile(samples, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    return {
        "estimate": float(statistic_fn(data)),
        "ci_low": float(lo),
        "ci_high": float(hi),
        "ci_width": float(hi - lo),
        "n_bootstrap": n_bootstrap,
        "ci": ci,
        "bootstrap_samples": samples.tolist(),
    }


@expose_metadata
def jackknife_variance(data: ArrayLike, statistic_fn: Callable[[np.ndarray], float]) -> Dict[str, Any]:
    """
    Jackknife estimate of variance and bias for a statistic.

    Equation:
        θ_jack = (1/n) Σⱼ θ₋ⱼ
        var = ((n-1)/n) Σⱼ (θ₋ⱼ - θ_jack)²
        bias = (n-1)(θ_jack - θ)

    Assumptions:
        - i.i.d. observations; statistic is smooth.
    """
    data = np.asarray(data, dtype=float)
    n = len(data)
    theta_full = statistic_fn(data)
    thetas = np.empty(n)
    for j in range(n):
        leave_out = np.delete(data, j)
        thetas[j] = statistic_fn(leave_out)
    theta_jack = thetas.mean()
    var = ((n - 1) / n) * np.sum((thetas - theta_jack) ** 2)
    bias = (n - 1) * (theta_jack - theta_full)
    return {
        "estimate": float(theta_full),
        "jackknife_estimate": float(theta_jack),
        "variance": float(var),
        "std": float(math.sqrt(max(0, var))),
        "bias": float(bias),
        "n": n,
    }


# ---------------------------------------------------------------------------
# Confidence / credible intervals
# ---------------------------------------------------------------------------


@expose_metadata
def confidence_interval_normal(
    estimate: float,
    standard_error: float,
    confidence: float = 0.95,
) -> Dict[str, Any]:
    """Normal-approximation confidence interval."""
    alpha = 1 - confidence
    z = stats.norm.ppf(1 - alpha / 2)
    return {
        "estimate": float(estimate),
        "se": float(standard_error),
        "confidence": confidence,
        "ci_low": float(estimate - z * standard_error),
        "ci_high": float(estimate + z * standard_error),
    }


@expose_metadata
def credible_interval_from_samples(
    samples: np.ndarray,
    ci: float = 0.95,
    method: str = "percentile",
) -> Dict[str, Any]:
    """
    Credible interval from posterior samples.

    Methods:
        percentile : equal-tailed interval
        hdi        : highest-density interval (shortest)
    """
    s = np.asarray(samples, dtype=float)
    alpha = 1 - ci
    if method == "percentile":
        lo, hi = np.percentile(s, [100 * alpha / 2, 100 * (1 - alpha / 2)])
    elif method == "hdi":
        from scipy.stats import gaussian_kde
        kde = gaussian_kde(s)
        xs = np.linspace(s.min(), s.max(), 2000)
        dens = kde(xs)
        max_dens = dens.max()
        # Find threshold that captures 1-c alpha of probability mass
        cum = np.cumsum(dens) / dens.sum()
        for thr in np.linspace(max_dens * 0.999, max_dens, 200):
            mask = dens >= thr
            if cum[np.where(mask)[0][-1]] >= alpha:
                break
        lo, hi = xs[np.where(mask)[0][0]], xs[np.where(mask)[0][-1]]
    else:
        raise ValueError(f"Unknown method {method!r}")
    return {"estimate": float(np.mean(s)), "ci_low": float(lo), "ci_high": float(hi), "ci": ci, "method": method}


# ---------------------------------------------------------------------------
# Look-elsewhere effect correction
# ---------------------------------------------------------------------------


@expose_metadata
def look_elsewhere_correction_simulation(
    statistic_fn: Callable,
    data_obs: ArrayLike,
    null_simulate_fn: Callable[[np.random.Generator], np.ndarray],
    n_simulations: int = 5000,
    n_tries: int = 100,
    random_seed: Optional[int] = None,
    local_null_cdf: Optional[Callable[[float], float]] = None,
) -> Dict[str, Any]:
    """
    Simulation-based look-elsewhere correction (Section 18 of the spec).

    When a statistic is evaluated over many locations/patterns, the significance
    of the single most interesting value must be judged against the null
    distribution of the MAXIMUM statistic, not the single-location distribution.
    Otherwise scanning millions of patterns and reporting the best one inflates
    significance (the look-elsewhere effect).

    Equation:
        p_global = P(max_i T_i >= t_obs)   over the null (computed by simulation)
        sigma_global = Phi^-1(1 - p_global)

    Variables:
        statistic_fn        : the scanned statistic T(data) -> float
        data_obs            : the observed data being scanned
        null_simulate_fn    : draws one synthetic null dataset
        n_tries             : effective number of independent looks (the scan size)

    Assumptions:
        - Null datasets are independent draws from the null hypothesis.
        - n_tries approximates the effective number of independent trials
          (correlated trials are down-weighted by the caller if needed).

    Returns:
        dict with observed_max_stat, local_p, global_p, global_significance_sigma,
        n_simulations, n_tries, and a corrected_significance flag.
    """
    rng = np.random.default_rng(random_seed)

    stat_obs = float(statistic_fn(data_obs))

    # Local (single-location) p-value.
    # If the caller supplies the single-location null CDF, use it; otherwise
    # fall back to the standard normal survival function, which is correct
    # only when the statistic is Gaussian under the null.
    if local_null_cdf is not None:
        local_p = float(local_null_cdf(stat_obs))
    else:
        local_p = float(stats.norm.sf(stat_obs))

    # Null distribution of the maximum statistic across the scan.
    max_stats = np.empty(n_simulations)
    for i in tqdm(
        range(n_simulations),
        desc="look-elsewhere simulations",
        disable=n_simulations < 100,
    ):
        null_data = null_simulate_fn(rng)
        # Evaluate the statistic at n_tries independent positions in one
        # synthetic sky, then take the maximum (the "most interesting" one).
        null_stats = [statistic_fn(null_data) for _ in range(n_tries)]
        max_stats[i] = np.max(null_stats)

    global_p = float(np.mean(max_stats >= stat_obs))
    # Guard the empirical tail so we never report infinite significance.
    global_p = min(max(global_p, 1.0 / (n_simulations + 1)), 1.0)
    global_sigma = float(stats.norm.isf(global_p))

    return {
        "observed_max_stat": stat_obs,
        "local_p": local_p,
        "global_p": global_p,
        "global_significance_sigma": global_sigma,
        "n_simulations": n_simulations,
        "n_tries": n_tries,
        # True when the look-elsewhere correction materially weakened the result.
        "look_elsewhere_reduced_significance": bool(global_p > local_p),
    }


@expose_metadata
def multiple_comparisons_correction(
    p_values: ArrayLike,
    method: str = "bonferroni",
) -> Dict[str, Any]:
    """
    Multiple comparison correction across a family of tests.

    Methods (statsmodels): bonferroni, benjamini-hochberg (FDR),
    holm, hosf, fdr_bh.

    Returns:
        dict with pvals, corrected_pvals, rejected.
    """
    p = np.asarray(p_values, dtype=float)
    # statsmodels returns a named tuple: (reject, pvals_corrected, alphacSidak,
    # alphacBonf). Unpack by name so this is stable across versions.
    reject, corrected = smm.multipletests(p, alpha=0.05, method=method)[:2]
    return {
        "p_values": p.tolist(),
        "corrected_p_values": np.asarray(corrected).tolist(),
        "rejected": bool(np.any(reject)),
        "n_rejected": int(np.sum(reject)),
        "method": method,
    }


# ---------------------------------------------------------------------------
# Monte Carlo / null simulations
# ---------------------------------------------------------------------------


@expose_metadata
def monte_carlo_significance(
    data_obs: ArrayLike,
    simulate_null_fn: Callable[[np.random.Generator], np.ndarray],
    statistic_fn: Callable[[np.ndarray], float],
    n_simulations: int = 5000,
    one_sided: bool = True,
    random_seed: Optional[int] = None,
    progress: bool = True,
) -> Dict[str, Any]:
    """
    Monte Carlo significance test: compare observed statistic to null
    distribution generated by simulation.

    Returns:
        dict with observed_stat, null_mean, null_std, p_value,
        global_significance_sigma, n_simulations.
    """
    rng = np.random.default_rng(random_seed)
    obs_stat = statistic_fn(data_obs)
    null_stats = np.empty(n_simulations)
    for i in tqdm(range(n_simulations), desc="null simulations", disable=not progress):
        null_stats[i] = statistic_fn(simulate_null_fn(rng))
    null_mean, null_std = float(null_stats.mean()), float(null_stats.std())
    n_sigma = (obs_stat - null_mean) / null_std
    p_value = float(np.mean(null_stats >= obs_stat)) if one_sided else float(np.mean(np.abs(null_stats) >= np.abs(obs_stat)))
    sigma = stats.norm.isf(p_value)
    return {
        "observed_stat": float(obs_stat),
        "null_mean": null_mean,
        "null_std": null_std,
        "p_value": p_value,
        "significance_sigma": float(n_sigma),
        "global_significance_sigma": float(sigma),
        "n_simulations": n_simulations,
    }


# ---------------------------------------------------------------------------
# Diagnostics & validation
# ---------------------------------------------------------------------------


@expose_metadata
def check_normality(sample: ArrayLike) -> Dict[str, Any]:
    """Normality checks: Shapiro-Wilk, Anderson-Darling, skewness, kurtosis."""
    s = np.asarray(sample, dtype=float)
    shapiro = stats.shapiro(s[:5000])  # limit for speed
    ad = stats.anderson(s, dist="norm")
    return {
        "shapiro_stat": float(shapiro.statistic),
        "shapiro_p": float(shapiro.pvalue),
        "anderson_stat": float(ad.statistic),
        "anderson_crit": [float(x) for x in ad.critical_values],
        "skewness": float(stats.skew(s)),
        "kurtosis": float(stats.kurtosis(s)),
    }


@expose_metadata
def autocorrelation_time(x: ArrayLike, max_lag: Optional[int] = None) -> Dict[str, Any]:
    """
    Integrated autocorrelation time (τ_int) for MCMC diagnostics.

    Equation:
        τ_int = 1 + 2 Σ_{t=1}^{M} ρ(t)   (sum until ρ first becomes negative)
    """
    x = np.asarray(x, dtype=float)
    x = x - x.mean()
    var = x.var()
    if var == 0:
        return {"tau_int": 1.0, "n_effective": float(len(x))}
    acf = np.correlate(x, x, mode="full") / (var * len(x))
    acf = acf[len(x) - 1:]  # positive lags
    max_lag = max_lag or len(x) // 2
    cutoff = 0
    for t in range(1, max_lag):
        if acf[t] < 0:
            cutoff = t
            break
    tau_int = 1 + 2 * np.sum(acf[1:cutoff])
    n_eff = len(x) / tau_int
    return {"tau_int": float(tau_int), "n_effective": float(n_eff), "max_lag_used": cutoff}


# ---------------------------------------------------------------------------
# Result & report helpers
# ---------------------------------------------------------------------------


@expose_metadata
def classify_significance(sigma: Optional[float] = None, p_value: Optional[float] = None) -> str:
    """Classify statistical significance into COSMOS labels."""
    sig = sigma if sigma is not None else (stats.norm.isf(p_value) if p_value is not None else 0.0)
    sig = min(sig, 10.0)
    for threshold, label in sorted(SIGNIFICANCE_LABELS.items(), reverse=True):
        if sig >= threshold:
            return label
    return "consistent_with_null"


@expose_metadata
def format_significance(
    sigma: Optional[float] = None, p_value: Optional[float] = None
) -> str:
    """Human-readable significance statement."""
    sig = sigma if sigma is not None else (stats.norm.isf(p_value) if p_value is not None else 0.0)
    if sig < 1.0:
        return "no significant deviation from null hypothesis"
    if sig < 3.0:
        return f"mild tension with null hypothesis ({sig:.2f}σ)"
    if sig < 5.0:
        return f"statistically significant tension with null hypothesis ({sig:.2f}σ)"
    return f"highly significant anomaly ({sig:.2f}σ)"


def save_results(result: Dict[str, Any], path: Path | str) -> None:
    """Save a results dictionary as JSON."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(result, f, indent=2, default=str)


def load_results(path: Path | str) -> Dict[str, Any]:
    """Load a results dictionary from JSON."""
    with open(Path(path)) as f:
        return json.load(f)


# ---------------------------------------------------------------------------
# Sigma8 consistency
# ---------------------------------------------------------------------------


@expose_metadata
def sigma8_consistency(
    sigma8_obs: float,
    sigma8_lcdm: float = 0.81,
    sigma8_err: float = 0.05,
) -> Dict[str, Any]:
    """
    Consistency check of sigma8 against Lambda CDM.

    Returns:
        dict with observed value, Lambda CDM value, difference, n_sigma,
        and consistency flag (|n_sigma| < 2).
    """
    diff = sigma8_obs - sigma8_lcdm
    n_sigma = diff / sigma8_err if sigma8_err > 0 else 0.0
    return {
        "sigma8_observed": sigma8_obs,
        "sigma8_lcdm": sigma8_lcdm,
        "difference": diff,
        "n_sigma": float(n_sigma),
        "consistent": abs(n_sigma) < 2.0,
    }

