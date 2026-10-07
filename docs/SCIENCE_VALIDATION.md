# Scientific Validation

Validation has two distinct meanings here, and conflating them is the mistake
that lets broken science ship with a green test suite.

1. **Internal validation** — does the code do what it claims? Does the P(k)
   estimator recover the P(k) it was given?
2. **External validation** — does our number agree with the published
   literature?

A suite can pass (1) completely and still be scientifically wrong, because the
same bug can be consistent end to end. (2) is what catches that.

## Internal validation (what the test suite covers)

245 tests. The physics-relevant ones:

### Known analytical values

| Assertion | Expected | Basis |
|---|---|---|
| `D(0)` | exactly 1.0 | Normalisation convention |
| `D(z=2)` | ≈ 0.17 | Carroll, Press & Turner 1992 |
| `E(0)` | exactly 1.0 | Closure constraint |
| `D_A` peak | z ≈ 1.6 | Standard expanding-cosmology result |
| `d_C(z=1)` | ≈ 3400 Mpc | Planck-calibrated cosmology |
| `c/H0` | ≈ 4448 Mpc at h=0.674 | Arithmetic |

### Round trips

| Assertion | Catches |
|---|---|
| Realised P(k) matches input P(k) | Wrong amplitude, missing Hermitian symmetry |
| σ8 recovered from the field's own P(k) | Wrong normalisation convention |
| Measured P(k) matches the field it sampled | FFT conventions, bias normalisation |
| Effective bias recovers a known input bias | Broken cross-spectrum |
| σ8 rescaling hits a target | Non-deterministic amplitude |

### Invariants

| Assertion | Catches |
|---|---|
| P(k) unchanged when `amplitude=0` | Spurious anisotropy |
| Anisotropy correlates with the requested axis's quadrupole | Wrong axis handling |
| `inject_and_recover` improves with lower noise | Inverted sensitivity |
| Detection fails for a sub-threshold signal | Over-claiming sensitivity |
| Bins above Nyquist raise | Silent clamping to fake zeros |
| Same seed → identical result | Non-determinism |

### Statistical methods

| Assertion | Catches |
|---|---|
| AIC, BIC match their formulas by hand | Wrong formula |
| Extra parameters are penalised | Rewarding complexity |
| `global_p >= local_p` for look-elsewhere | Under-corrected significance |
| A 4.5σ single-location peak is not a discovery after scanning | p-hacking |
| Bootstrap CI narrows with sample size | Wrong resampling |
| `tau_int` recovered from an AR(1) process | Misreading MCMC convergence |

## External validation (status)

**One component performed, one blocked.**

### Performed: BAO distance measures against DESI DR2

`cosmos/cosmology.py` computes D_H = c/H(z), D_M (transverse) and D_V
(volume-averaged) for a flat cosmology, and was checked against the DESI DR2
BAO vectors retrieved from the CobayaSampler mirror (arXiv:2503.14738,
2503.14739):

| Quantity | Agreement | Verdict |
|---|---|---|
| `DH_over_rs` at z = 2.330 | 1.1% | reproduced |
| `DH_over_rs` across z = 0.51 to 2.33 | 4.0% worst case, -0.2% at high z | reproduced |
| `DM_over_rs` at z = 2.330 | 70% discrepancy | **not reproduced** |

The D_H residual is not an error: the model uses Planck 2018 parameters while
DESI fits its own cosmology, and the difference is largest at low z where the
expansion history is most parameter-sensitive.

The D_M result is a genuine open problem rather than a failed fit. The same
labelled values reproduce the model's *comoving* distance D_C/r_s to 1%, so the
column is not random — it appears to hold D_C where the label says D_M. The
available documentation does not settle which it is, so no model is fitted to
it. Details in `docs/DATA_SOURCES.md`; the finding is an executable assertion
in `tests/test_cosmology.py::TestDESIColumnConvention`.

Note what this validation did and did not do: it checked our distance
calculation against the data, and it found a problem in the data mirror. It did
not validate a cosmological inference, because no inference was made.

### Not performed: cosmological parameter inference

No experiment has yet fit a cosmological model to an observation and been
checked against a published result. When that happens, the protocol (§41 of the
specification) is:

1. Record the published value and its uncertainty
2. Record ours and its uncertainty
3. Compute the difference and the combined uncertainty
4. Test compatibility
5. **If they disagree, investigate why — do not adjust the pipeline until it
   agrees**

Step 5 is the whole point. Tuning code until it reproduces a target number
destroys the independence that makes the comparison meaningful.

## Injection and recovery as validation

The strongest internal check is that the pipeline recovers a signal of known
amplitude from known noise. EXP-001 runs this on every execution:

```
- Feature: Gaussian bump at k = 0.05 h/Mpc
- Injected amplitude: 0.464
- Signal-to-noise: 5.00
- Detected: True
- False-positive rate: 0.016  (target 0.02)
```

The false-positive threshold scales with the number of bins. An earlier version
used a fixed 3σ-per-bin threshold, which produced a 99.5% false-positive rate —
the test caught it, and fixing it is what the "acceptable" verdict now rests on.

## Honest reporting of limits

The committed EXP-001 run reports:

- `survived: False` in the adversarial stage, because the highest-k bin carries
  69% of the chi-square — the linear prediction is least valid there
- Unquantified systematics (galaxy selection, redshift-space distortions), with
  the significance declared an upper bound on the evidence
- The naive chi-square disagreeing with the Monte Carlo test, with the
  explanation that Poisson errors understate the true uncertainty

These are reported rather than smoothed over. A validation framework that only
surfaces good news is not validating anything.

## What would count as external validation

The first genuine opportunity is EXP-001 on a published power spectrum:

| Quantity | Source | Precision needed |
|---|---|---|
| Matter power spectrum | BOSS DR12 consensus | ~1% per bin |
| σ8 | Planck 2018 | 0.006 |
| H0 (local) | SH0ES | ~1 km/s/Mpc |
| BAO scale | BOSS + WiggleZ | ~1% |

If the pipeline recovers these within their uncertainties from public data, it
has demonstrated external validity. Until then it is internally validated
only, and should be described that way.