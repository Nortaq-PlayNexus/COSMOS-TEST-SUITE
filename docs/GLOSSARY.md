# Glossary

Plain-language definitions for every term used in the interface. §56 of the
specification requires that every technical term in the UI be explainable.

---

**Anisotropy** — The universe not looking the same in every direction. A dipole
is the simplest kind.

**BAO (Baryon Acoustic Oscillation)** — A frozen ripple in the early universe,
~150 million years after the Big Bang, that stretched as space expanded. Visible
today as a characteristic spacing in galaxy clustering, giving a standard-ruler
measurement of cosmic expansion.

**BBKS** — An analytic approximation to the matter power spectrum in a
cosmology dominated by matter and dark energy. Older and cruder than a full
Boltzmann code, but instant.

**Bias (galaxy bias)** — Galaxies do not trace matter perfectly. Galaxies
preferentially form in dense regions, so `b ≈ 1.2` means a 10% matter
overdensity hosts roughly 12% more galaxies. Measured, not assumed.

**BIC** — Bayesian Information Criterion. A model-comparison measure that
penalises parameters: `k ln(n) − 2 ln L`. Prefers simplicity.

**Bubble universe / bubble collision** — In eternal inflation, inflating space
can nucleate new "bubble" universes. Colliding bubbles would leave circular
temperature signatures in the CMB. **Speculative** — treated as such throughout.

**Chi-square (χ²)** — A measure of how far observations sit from a prediction.
Smaller is better; roughly how many standard deviations of disagreement.

**CMB (Cosmic Microwave Background)** — The afterglow of the Big Bang, released
when the universe became transparent ~380,000 years in. Now a 2.725 K microwave
background, with ~10⁻⁵ K fluctuations.

**Cosmic variance** — With only one observable universe, some questions have an
irreducible statistical floor. Cannot be reduced by more data.

**Cosmic web** — The filamentary, web-like arrangement of galaxies and dark
matter traced by large surveys.

**Cosmic variance** — see above.

**Dark energy** — The component driving the observed accelerated expansion.
About 68% of the energy density. Identity unknown.

**Dark matter** — Matter inferred from gravitational effects but not
electromagnetically observed. About 26% of the energy density.

**D_A (Angular diameter distance)** — `D_C / (1+z)`. Peaks at z ≈ 1.6, which is
why the most distant resolved objects are not the largest objects.

**Δ² (Dimensionless power spectrum)** — `k³ P(k) / 2π²`. A convenient
scale-free measure of clustering amplitude.

**E(z)** — `H(z)/H0`. Equals exactly 1 at z = 0 by construction here.

**Expansion factor / scale factor (a)** — `a = 1/(1+z)`. Equals 1 today and 0
at the Big Bang.

**False positive rate** — How often the analysis reports a signal when none is
present. Measured directly by injecting noise-only realisations.

**Fiducial model** — The model taken as reference to which others are compared.
Usually ΛCDM.

**Flat** — Spatial curvature zero, so the universe has zero net curvature.

**FLRW** — The standard homogeneous and isotropic cosmological model, named
after Friedmann, Lemaître, Robertson, and Walker.

**Gaussian random field** — A field whose values are independent Gaussian
variables. Sufficient statistics for linear perturbations under Gaussian
initial conditions.

**Growth factor D(z)** — How matter perturbations grow between the early
universe and now. `D(0) = 1`.

**Homogeneity** — The universe looking the same from every location, as opposed
to *isotropy* (same from every direction).

**Hubble constant H0** — Present-day expansion rate, ~67–74 km/s/Mpc depending
on method. The tension between early- and late-universe values is unresolved.

**Hubble distance** — `c/H0`. ~4448 Mpc for H0 = 67.4.

**Inflation** — A period of accelerated expansion in the very early universe.
Proposed to solve several problems; not directly observed.

**Injected signal / injection and recovery** — Planting a known signal in
synthetic data to verify the pipeline would detect it. Run before interpreting
any real result.

**Isotropy** — Same from every direction.

**LambdaCDM (ΛCDM)** — The standard model: cosmological constant (Λ) for dark
energy, cold dark matter, standard baryon density.

**Look-elsewhere effect** — Scanning many parameters or locations and reporting
the most interesting result inflates apparent significance. Corrected by
comparing against the null distribution of the *maximum* statistic.

**Matter power spectrum P(k)** — Clustering amplitude as a function of scale.
The core observable in EXP-001.

**MCMC** — Markov Chain Monte Carlo. Samples a posterior by proposing moves and
accepting according to the target distribution. Convergence must be diagnosed.

**Non-Gaussianity** — Departure of the primordial perturbation distribution from
Gaussian. A testable signature of inflation.

**Nuisance parameter** — A parameter not of scientific interest, fitted only to
absorb an unmodelled effect.

**Nyquist wavenumber** — The highest wavenumber a grid of spacing `a` can
resolve: `k_Nyq = π/a`. Requesting more is an error, not a silent clamp.


**Parametric bootstrap** — Simulating under a fitted model to build a null
distribution.

**P(k)** — see Matter power spectrum.

**P-value** — Probability of observing data at least this extreme, **assuming
the null hypothesis is true**. Not the probability the null is true.

**Periodic box** — A simulation box with opposite faces identified, so the field
wraps seamlessly and there are no boundary effects.

**Poincaré dodecahedron** — A possible compact topology for the universe.

**Posterior predictive check** — Comparing model-generated data to the observed
data after fitting, to check the model can reproduce what was seen.

**Power-law spectrum** — `P(k) ∝ k^α` with constant α across scales.

**Pre-registration** — Writing the analysis plan — steps, seed, timestamp —
before examining the data. Structural guard against HARKing.

**Primordial gravitational waves** — Tensor perturbations from inflation,
potentially leaving B-mode polarisation in the CMB. Not detected.

**QCD** — Quantum chromodynamics. The theory of the strong nuclear force.

**Reconstruction** — Inferring the three-dimensional density field from
projected galaxy positions.

**Redshift** — `z = (λ_obs − λ_emit)/λ_emit`. A measure of recession.

**Robustness** — Whether a result survives different reasonable analysis
choices: alternative estimators, datasets, and systematics models.

**S8** — The normalisation of clustering, `σ8 · sqrt(Ω_m/0.3)`.

**Scale-dependent bias** — Bias that varies with wavenumber.

**Selection function** — The probability an object enters a survey given its
true properties. A major systematic.

**Shot noise** — Poisson noise from sampling a finite number of objects. Sets
the floor `1/nbar` on P(k).

**Sigma (σ)** — Standard deviations. 1σ = 68%, 2σ = 95%, 3σ = 99.7%. In
astronomy, the discovery threshold is **5σ**, not 3σ.

**σ8** — RMS matter fluctuation in a sphere of radius 8 Mpc/h. ~0.81.



**Spectral index n_s** — The slope of the primordial scalar power spectrum.
~0.965.

**Systematics** — Effects other than the signal of interest that bias a
measurement. Must be enumerated and, ideally, quantified.

**Tensor-to-scalar ratio (r)** — Amplitude of primordial gravitational waves
relative to scalar perturbations.

**Top-hat window** — `W(x) = 3(sin x − x cos x)/x³`. Fourier transform of a
sphere; used to define σ_R.

**Topology** — The global shape of space. Compact topologies make space finite
even without curvature.

**Transfer function** — `T(k)`, the ratio of the matter power spectrum to a
scale-invariant primordial spectrum. Encodes suppression of small scales by
decoupling physics.


**Uncertainty propagation** — How input uncertainties become output
uncertainties.

**Variance** — Spread of a quantity around its mean; the square of the standard
deviation.

**Volume** — In these docs, the comoving box size in Mpc/h.


**Wavenumber (k)** — Spatial frequency, `2π/r` in units of h/Mpc.

**z, redshift** — see Redshift.

---

## Vocabulary the project commits to

These are not scientific terms but the project's own guarantees:

| Term | Meaning here |
|---|---|
| **SUPPORTED** | Data do not disfavour the hypothesis; no evidence against |
| **DISFAVORED** | Data disfavour the hypothesis |
| **INCONCLUSIVE** | Ambiguous; more data needed |
| **CONSISTENT_WITH_STANDARD_MODEL** | Agrees with ΛCDM within uncertainty |
| **STATISTICALLY_SIGNIFICANT_ANOMALY** | Significant, sensitive, pre-registered |
| **LIKELY_SYSTEMATIC** | Apparent signal better explained by an analysis artefact |
| **REQUIRES_REPLICATION** | Needs independent confirmation before interpretation |
| **NOT_TESTABLE** | No current data can address it |
| **INSUFFICIENT_DATA** | Test is possible but data is inadequate |
| **UNKNOWN** | Genuinely unknown — a valid result |

Words the project does not use: "proves", "confirms" (for a theory),
"discovered" (below 5σ), or any number without an uncertainty attached.