# Statistics

Every function in `cosmos/statistics/` documents its equation, variables,
units, assumptions, numerical method, and validation.

## Model comparison

| Function | Formula |
|---|---|
| `compute_aic(n, k, log_likelihood)` | `AIC = 2k − 2 ln L`, plus the small-sample correction |
| `compute_bic(n, k, log_likelihood)` | `BIC = k ln n − 2 ln L` |
| `model_weights(aic, bic)` | Akaike and Bayesian weights from ΔAIC |
| `bayes_factor(ln Z_A, ln Z_B)` | `BF = exp(ln Z_A − ln Z_B)` |

Parameters are penalised. A test asserts that a model fitting marginally better
with 23 extra parameters is **not** preferred by BIC — the specification is
explicit that flexibility alone must not win.

Bayes factor interpretation (Kass & Raftery 1995):

```
ln BF   0–1   not worth a bare mention
       1–3   positive
       3–5   strong
        >5   decisive
```

## Hypothesis tests

`chi_square_test`, `kstest_two_sample`, `ttest_independent`,
`permutation_test`.

Permutation tests are preferred for small samples or unknown distributions: they
make no distributional assumption and stay exact under exchangeability.

## Uncertainty

| Function | Use |
|---|---|
| `bootstrap_confidence_interval` | Non-parametric CIs; tested to shrink with sample size |
| `jackknife_variance` | Bias and variance for smooth statistics |
| `confidence_interval_normal` | Normal approximation |
| `credible_interval_from_samples` | Posterior intervals, `percentile` or `hdi` |

The HDI method returns the narrowest interval containing the target mass.

## Multiple comparisons

```python
multiple_comparisons_correction(p_values, method="bonferroni")
```

Methods: `bonferroni`, `holm`, `fdr_bh`, and others via statsmodels. Bonferroni
is conservative; FDR controls the expected false discovery rate.

## Look-elsewhere effect

This is the correction the specification insists on, and the one most often
skipped in practice.

Scanning a million patterns and reporting the best one inflates significance. The
correction compares the observed **maximum** statistic against the null
distribution of the maximum, not the single-location distribution:

```python
res = look_elsewhere_correction_simulation(
    statistic_fn, data_obs, null_simulate_fn,
    n_simulations=5000, n_tries=100,
)
res["local_p"]               # naive, ignores the scan
res["global_p"]              # corrected for scanning
res["global_significance_sigma"]
```

`global_p >= local_p` always holds. A test asserts that a 4.5σ single-location
excursion found by scanning 40 positions is not reported as significant.

The empirical tail is guarded at `1/(n_simulations+1)`, so a finite simulation
never produces an infinite significance.

## Monte Carlo

```python
monte_carlo_significance(
    data_obs, simulate_null_fn, statistic_fn,
    n_simulations=5000,
)
```

Every experiment should be able to say *"here is what the universe would look
like if the null hypothesis were true."*

## Diagnostics

| Function | Purpose |
|---|---|
| `autocorrelation_time` | Integrated τ for MCMC chains |
| `check_normality` | Shapiro-Wilk, Anderson-Darling, skew, kurtosis |
| `classify_significance` | Maps σ to a COSMOS label |
| `format_significance` | Human-readable phrasing that avoids "proves" |

`autocorrelation_time` is what stops a short MCMC chain being mistaken for a
long one. A test feeds it an AR(1) process and asserts τ is recovered as large.

## Guardrails against statistical malpractice

The specification lists the failure modes to defend against. Where each is
handled:

| Failure mode | Defence |
|---|---|
| p-hacking | Pre-registered analysis plan, enforced by call order |
| HARKing | Same — the plan is written before the statistic exists |
| Cherry-picking | Decision rule fixed in `_classify()` in advance |
| Look-elsewhere | `look_elsewhere_correction_simulation` |
| Multiple comparisons | `multiple_comparisons_correction` |
| Data leakage | `raw/` is append-only; processing never writes to it |
| Overfitting | BIC penalisation; held-out data where practical |
| Model-selection bias | Bayesian weights reported alongside AIC |
| Publication bias | Null and negative results are first-class outputs |

## Significance thresholds

```
< 1σ   consistent with null
 1–3σ  moderate evidence
 3–5σ  strong evidence
   5σ  discovery
 >10σ  overwhelming
```

The discovery threshold is **5σ**, not 3σ. This is deliberate: at 3σ, scanning
enough parameters produces false discoveries routinely.