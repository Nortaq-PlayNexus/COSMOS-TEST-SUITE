# Simulations

The simulation engine exists for one reason stated in the specification: it is
essential for calculating false-positive rates. A pipeline that cannot show what
the null hypothesis looks like cannot interpret its own results.

## Cosmology calculator

`Cosmology` is self-contained — no external cosmology library.

```python
from cosmos.simulations import Cosmology
c = Cosmology(h=0.674, om=0.315, ol=0.685)
c.hubble_radius          # c/H0 in Mpc
c.e(z)                   # H(z)/H0, exactly 1 at z=0
c.comoving_distance(z)
c.angular_diameter_distance(z)
c.growth_factor(z)       # D(z), D(0) = 1
c.linear_power_spectrum(k)
```

**Closure constraint.** `E(0) = 1` exactly, because curvature is derived as
`Ω_k = 1 − Ω_m − Ω_L − Ω_r` rather than set independently. Choosing parameters
that do not sum to unity does not silently break the normalisation.

**Validated against known values** (tests assert each):

| Quantity | Expected | Verified |
|---|---|---|
| `D(0)` | 1.0 | ✓ |
| `D(z=2)` | ≈ 0.17 | ✓ |
| `D_A` peak | z ≈ 1.6 | ✓ (1.588) |
| `d_C(z=1)` | ≈ 3400 Mpc | ✓ (3401) |
| `c/H0` at h=0.674 | ≈ 4448 Mpc | ✓ |

## Power spectrum convention

Getting P(k) right took several corrections that the tests now guard.

```
P(k) = <|fftn(delta)|^2| * V_cell / N
```

Two factors are easy to get wrong, and both were wrong at some point:

1. **Divide by N, not by V.** `n_cells = n³`.
2. **Multiply by `V_cell = (L/n)³`.** Without it, P(k) is in units of variance
   per cell instead of (Mpc/h)³.

Sanity check that catches both: for white noise, σ_R² must equal the continuum
variance `V_cell · ⟨δ²⟩`.

## Gaussian random fields

```python
from cosmos.simulations import GRFConfig, generate_grf
field = generate_grf(GRFConfig(cosmo=c, box=400., nside=32,
                                k_min=0.02, k_max=0.25,
                                seed=42, sigma8=0.81))
```

Amplitude convention:

```
E[|F_k|²] = N · P(k) / V_cell
```

with Hermitian symmetry `F(−k) = conj(F(k))` imposed by assigning amplitudes to
one representative of each ±k pair. Without the symmetry the inverse transform
is complex and its real part has half the intended power — the field looks
like white noise.

**The field is not standardised to unit variance.** Doing so dumps variance into
modes near the Nyquist limit, which alias back into the low-k bins and corrupt
P(k). Instead the input spectrum is σ8-normalised, then the field is rescaled to
hit the requested σ8 exactly, removing single-realisation cosmic variance from
the amplitude.

Verified: the realised P(k) matches the input spectrum to within 12% scatter
across the shell, consistent with cosmic variance in one realisation.

## Mock galaxy catalogues

```python
from cosmos.simulations import clustered_mock_galaxy_catalog
mock = clustered_mock_galaxy_catalog(
    box=400., n_grid=48, nbar=0.05, bias=0.3,
    cosmo=c, seed=42, target_sigma8=0.81,
)
```

Procedure:

1. Generate a periodic ΛCDM density field
2. Apply the bias relation, `ρ ∝ 1 + b δ`, clipped at zero
3. Sample `nbar · V` Poisson galaxies in proportion to that density

**Bias is measured, not assumed.** Clipping empty cells reduces clustering
below the input bias, so `effective_bias()` computes it from the fields:

```
b_eff = Σ δ_g(k) δ_m(k) / Σ |δ_m(k)|²
```

A test confirms it recovers a known input bias and that shot noise does not bias
it.

## Power spectrum measurement

```python
from cosmos.simulations import measure_power_spectrum
ps = measure_power_spectrum(positions, box=400., n_grid=48, k_min=0.02)
ps["p_k"], ps["p_k_err"], ps["n_modes"], ps["shot_noise"]
```

Uncertainties combine Poisson noise and sampling variance:
`σ_P = (P + 1/nbar) / sqrt(N_modes)`.

Two densities are in play and conflating them is a silent error:

- `nbar` — galaxies per (Mpc/h)³, sets the shot-noise floor
- `nbar_cell` — galaxies per cell, normalises the density contrast to zero mean

Requesting `k_max` above the grid Nyquist wavenumber raises rather than
silently clamping, because clamping returns empty shells as zero power.

## Other models

| Model | Function |
|---|---|
| Anisotropic | `anisotropic_field` — ℓ=2 quadrupole along a preferred axis |
| Finite topology | `periodic_field`, `matched_circles_signature` — 3-torus |
| Bubble collision | `bubble_collision_template`, `inject_and_recover` |
| Modified gravity | `altered_gravity_field`, `altered_power_spectrum` |
| Mock (simple) | `mock_galaxy_catalog` — redshift-space, no clustering |

## Dark energy

```python
from cosmos.simulations import DECosmology
de = DECosmology(h=0.674, om=0.315, ol=0.685, w0=-0.9, wa=0.0, model="w_const")
```

Evolves ρ_de with the continuity equation `d ln ρ_de/dz = 3(1+w)/(1+z)`.
For `w = −1` this vanishes, reproducing a true cosmological constant.

Validated: `w = −0.9` yields a larger `E(z)` than `w = −1` at z = 0.5, which is
the mechanism by which evolving dark energy can fit expansion history better.

## Injection and recovery

```python
from cosmos.simulations import bubble_collision_template, inject_and_recover
t = bubble_collision_template(nlat=64, r0=0.15)
res = inject_and_recover(t, noise_sigma=2e-6, n_injections=100)
```

Matched filter against a matched-shape template. Sensitivity must increase
monotonically with signal-to-noise — asserted by test, because a detector that
recovers a weak signal better than a strong one is broken.

## Reproducibility

Every simulation carries a `reproducibility_hash()` derived from its name,
model, parameters, and seed. Two runs with the same configuration produce the
same hash; changing the seed changes it.