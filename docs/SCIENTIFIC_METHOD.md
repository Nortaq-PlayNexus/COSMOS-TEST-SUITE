# Scientific Method

The governing principle of this project:

> **Do not try to prove a theory. Try to find out whether the data can disprove it.**

A hypothesis earns standing by surviving attempts to break it. Every design
decision below follows from that.

## Separating the four kinds of statement

The system distinguishes, and labels, four things that are routinely conflated:

| Label | Meaning | Example |
|---|---|---|
| **Observation** | What was measured | "P(k) = 1300 ± 60 (Mpc/h)³ at k = 0.1" |
| **Inference** | What the model implies | "consistent with ΛCDM at 0.5σ" |
| **Hypothesis** | A proposed explanation | "the spectrum follows BBKS" |
| **Speculation** | No current test | "the universe is infinite" |

The report generator cannot write "proves". A test asserts the word never
appears, and a separate test asserts that any run on synthetic data states so
explicitly.

## Pre-registration

The analysis plan — the list of steps, the seed, the timestamp, the commit — is
written before any statistic is computed. `register_analysis_plan()` runs at
step 2 of the pipeline; `_prepare_data()` runs at step 3.

This is the structural guard against HARKing. It is not a promise in a README;
it is enforced by the order of calls in `ExperimentRunner.run()`, and a test
asserts the ordering.

## Choosing the statistic before seeing the data

EXP-001 fixes its decision rule in `_classify()` ahead of time:

```
p >= 0.05        -> CONSISTENT_WITH_STANDARD_MODEL
0.001 <= p < 0.05 -> INCONCLUSIVE
p < 0.001        -> STATISTICALLY_SIGNIFICANT_ANOMALY, but only if
                    injection-recovery confirms the pipeline was sensitive;
                    otherwise LIKELY_SYSTEMATIC
```

The injection-recovery gate matters: a pipeline that cannot detect a planted
signal has no standing to report its absence as evidence.

## Injection and recovery

Before interpreting any real signal, the pipeline must show it would have found
one. EXP-001 plants a Gaussian bump in P(k), scaled to a target signal-to-noise
ratio, and confirms detection. It also measures the false-positive rate on
noise-only realisations.

This inverts the usual failure mode. Without it, a null result is
indistinguishable from an instrument that does not work.

## Monte Carlo calibration over analytic p-values

EXP-001 does **not** trust its nominal chi-square p-value. The per-bin Poisson
uncertainties ignore the sampling variance of the field realisation itself,
which for one realisation of a 400 Mpc/h box dwarfs the Poisson term.

So the statistic is recalibrated against synthetic ΛCDM skies. This is visible
in the actual output of a good run:

```
chi-square p = 0.0    Monte Carlo p = 0.295
```

The naive chi-square says "significant". It is wrong, and the adversarial stage
is designed to surface exactly this kind of disagreement. The Monte Carlo
value is the one used for classification.

## Look-elsewhere correction

Scanning a million patterns and reporting the most interesting one inflates
significance. `look_elsewhere_correction_simulation()` computes the null
distribution of the **maximum** statistic over a scan and returns the
look-elsewhere-corrected significance alongside the naive local one.

The corrected p-value is always ≥ the local p-value. `bonferroni` and FDR
corrections are available for families of tests. A test asserts a 4.5σ
single-location excursion does not survive as a discovery after scanning 40
positions.

## Adversarial review

Every result is attacked before it is reported. EXP-001 asks six questions and
answers each with an actual computation rather than a checklist:

1. Is the result driven by a single bin?
2. Would pure noise produce a chi-square this large?
3. Would the pipeline have found a real injected feature?
4. How often does the detector fire on noise alone?
5. Was the analysis pre-registered?
6. Do the two statistics agree?

Findings that contradict the result are reported as findings. In the committed
EXP-001 run, `survived` is `False` because the highest-k bin carries 69% of the
chi-square — the linear prediction is least valid there. That is reported, not
buried.

## Unquantified systematics are declared

Systematics are tabulated with a `quantified: true/false` flag. Unquantified
ones are listed separately and the report states that the significance is an
upper bound on the evidence. In the committed run, galaxy selection and
redshift-space distortions are flagged unquantified.

## Honest failure

The classification vocabulary includes `NOT_TESTABLE`, `INSUFFICIENT_DATA`,
`INCONCLUSIVE`, and `LIKELY_SYSTEMATIC`. These are not error states — they are
results. A pipeline that cannot answer says so, and says why.

## What this method has and has not demonstrated

Stated plainly, because the distinction is the whole point:

- The power spectrum estimator recovers the P(k) of the field it sampled, within
  measurement uncertainty. Tested.
- The ΛCDM calculator reproduces known values: D(0) = 1, the angular diameter
  distance peaks at z ≈ 1.59, σ8 round-trips through the estimator. Tested.
- Injection-and-recovery sensitivity is monotonic in signal-to-noise. Tested.
- The pipeline runs end-to-end from a clean clone. Tested.

- **No conclusion has been drawn about the physical universe.** EXP-001 has only
  ever consumed synthetic data. Every one of the 35 research questions in the
  specification remains open.