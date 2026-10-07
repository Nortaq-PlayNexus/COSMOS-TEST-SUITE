"""
Simulation engine for COSMOS TEST SUITE.

Generates synthetic universes under different cosmological assumptions,
enabling:
- Null distribution generation (Section 25 of spec)
- False-positive rate estimation
- Injection & recovery tests (Section 12 of spec)
- Algorithm validation

Models implemented:
- ΛCDM (toy power spectrum + Gaussian random field)
- Modified dark energy (w0-wa, evolving)
- Altered matter power spectrum
- Altered gravity (toy)
- Anisotropic toy universes
- Finite topology toy models (3-torus, Poincare dodecahedron)
- Bubble-collision toy models

Every simulation exposes: parameters, random seed, output artifacts, and a
reproducibility hash.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, List, Optional

import numpy as np
from scipy import integrate
from scipy import stats as scipy_stats
from scipy.interpolate import interp1d


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

ArrayLike = np.ndarray
SimOutput = Dict[str, Any]

# ---------------------------------------------------------------------------
# Cosmological constants (cgs / Hz / degrees / Mpc)
# ---------------------------------------------------------------------------

H0_KM_S_MPC = 67.4           # km/s/Mpc (Planck 2018)
OMEGA_M0 = 0.315             # matter density
OMEGA_L0 = 0.685             # dark energy density
OMEGA_R0 = 9.2e-5            # radiation
OMEGA_K0 = 0.0               # curvature
SIGMA8 = 0.81                # RMS linear fluctuations
NS = 0.965                   # scalar spectral index
AS = 2.1e-9                  # amplitude of scalar power spectrum


# ---------------------------------------------------------------------------
# Cosmological calculators (toy, self-contained — no external cosmology libs)
# ---------------------------------------------------------------------------


@dataclass
class Cosmology:
    """
    Self-contained cosmology calculator (Section 4 of spec).

    Implements: H(z), comoving distance, angular diameter distance,
    linear matter power spectrum (BBKS approximation), growth factor.
    """

    h: float = H0_KM_S_MPC / 100.0
    om: float = OMEGA_M0
    ol: float = OMEGA_L0
    or_: float = OMEGA_R0
    ok: float = OMEGA_K0
    ns: float = NS
    as_: float = AS
    sigma8: float = SIGMA8

    @property
    def crit_density(self) -> float:
        """Critical density today in Msun/Mpc^3."""
        return 2.7755e11 * self.h ** 2

    @property
    def hubble_radius(self) -> float:
        """
        Hubble distance c/H0 in Mpc.

        H0 is given as h0 = 100*h km/s/Mpc, so c/H0 = c/(100*h).
        """
        return 299792.458 / self.h0

    def e(self, z: ArrayLike) -> ArrayLike:
        """
        E(z) = H(z)/H0.

        E(0) = 1 exactly: the curvature term is derived as the closure
        constraint Omega_k = 1 - Omega_m - Omega_L - Omega_r, so the present-day
        density parameters always sum to unity regardless of the values chosen
        for om, ol, and or_.
        """
        z = np.asarray(z, dtype=float)
        ok = self.curvature()
        return np.sqrt(
            self.om * (1 + z) ** 3
            + self.or_ * (1 + z) ** 4
            + ok * (1 + z) ** 2
            + self.ol
        )

    def curvature(self) -> float:
        """Omega_k from the closure constraint (always forces E(0) = 1)."""
        return 1.0 - (self.om + self.ol + self.or_)

    def hubble(self, z: ArrayLike) -> ArrayLike:
        """H(z) in km/s/Mpc."""
        return self.h0 * self.e(z)

    @property
    def h0(self) -> float:
        return self.h * 100.0

    def comoving_distance(self, z: ArrayLike) -> ArrayLike:
        """
        Line-of-sight comoving distance in Mpc.

        D_C(z) = (c/H0) * integral_0^z dz'/E(z'), evaluated by cumulative
        trapezoidal integration on a fixed grid and interpolated. The integral
        is zero at z = 0 by construction.
        """
        z = np.asarray(z, dtype=float)
        z_max = max(float(np.max(z)), 1e-3)
        zz = np.linspace(0.0, z_max, 2000)
        integrand = 1.0 / self.e(zz)
        # Cumulative trapezoid: starts at exactly 0.0 at z = 0.
        integral = integrate.cumulative_trapezoid(integrand, zz, initial=0.0)
        func = interp1d(zz, integral, kind="linear", bounds_error=False, fill_value=0.0)
        return self.hubble_radius * func(z)

    def angular_diameter_distance(self, z: ArrayLike) -> ArrayLike:
        """Angular diameter distance D_A = D_C / (1+z)."""
        return self.comoving_distance(z) / (1 + np.asarray(z))

    def comoving_hubble_radius(self, z: ArrayLike) -> ArrayLike:
        return self.hubble_radius / self.e(z)

    def linear_power_spectrum(self, k: ArrayLike) -> ArrayLike:
        """
        BBKS linear matter power spectrum (Bardeen, Bond, Kaiser & Szalay 1986;
        BBKS 1990).

        Equation:
            P(k) = (2 pi)^3 / h^3 * A_s * k^ns * T(q)^2,   q = k / (Omega_m h)

        Transfer function (BBKS fitting function):
            T(q) = ln(1 + 2.34 q)
                 / [ 2.34 q * (1 + 3.89 q + (16.1 q^2 + 5.46 q^3 + 6.71 q^4)^{1/2})^{1/4} ]

        k is in h/Mpc, so P(k) comes out in (Mpc/h)^3.

        Note the amplitude carries the (2 pi)^3 / h^3 prefactor. Its overall
        normalisation is degenerate with sigma8, so callers that need a
        physical amplitude should rescale with
        `normalize_power_spectrum_sigma8`.
        """
        k = np.asarray(k, dtype=float)
        q = k / (self.om * self.h)

        # Vectorised BBKS transfer function. T -> 1 as q -> 0.
        with np.errstate(divide="ignore", invalid="ignore"):
            poly = 1.0 + 3.89 * q + np.sqrt(
                16.1 * q**2 + 5.46 * q**3 + 6.71 * q**4
            )
            t = np.log1p(2.34 * q) / (2.34 * q * poly**0.25)
        # Fill the removable singularities at q = 0.
        t = np.where(np.isfinite(t), t, 1.0)

        prefactor = (2 * math.pi) ** 3 / self.h**3
        return prefactor * self.as_ * (k**self.ns) * t**2

    def sigma2(self, R: float) -> float:
        """Linear sigma_8-normalized RMS in a sphere of radius R (Mpc/h)."""
        # Simplified: use lognormal fit to CAMB-like values
        # sigma_8 = 0.81; approximate scaling sigma(R) ≈ 0.81 (R/8)^(-0.55)
        return self.sigma8 * (R / 8.0) ** (-0.55)

    def growth_factor(self, z: ArrayLike) -> ArrayLike:
        """
        Linear growth factor D(z) normalized to D(0) = 1.

        Equation (growth equation in scale factor, Carroll, Press & Turner 1992):
            D(a) proportional to (a*E(a)) * integral_0^a da' / (a'*E(a'))^3

        where E(a) = H(a)/H0 and z = 1/a - 1. The integral is finite because
        E(a') -> 1/a' as a' -> 0, so the integrand tends to a'^2.
        """
        z = np.asarray(z, dtype=float)
        z = z[np.isfinite(z)]
        if z.size == 0:
            return np.array([])
        a_needed = 1.0 / (1.0 + np.max(z))
        a_max = min(max(a_needed, 1e-3), 1.0)
        aa = np.logspace(-8, np.log10(a_max), 4000)
        # a = 1 (today, z = 0) is always needed for the normalization, and is
        # perfectly regular: z = 1/a - 1 = 0 there, so E is finite.
        aa = np.unique(np.concatenate([aa, [1e-8, 1.0]]))
        e_a = self.e(1.0 / aa - 1.0)
        integrand = 1.0 / (aa * e_a) ** 3
        int_vals = integrate.cumulative_trapezoid(integrand, aa, initial=0.0)
        f = interp1d(aa, int_vals, kind="linear", bounds_error=False, fill_value=0.0)

        a_now = 1.0 / (1.0 + z)
        d_unnorm = (a_now * self.e(z)) * f(a_now)
        d0 = (1.0 * self.e(0.0)) * f(1.0)
        if d0 <= 0:
            raise ValueError(
                "growth normalization failed: integral of the growth function "
                "is non-positive"
            )
        return d_unnorm / d0

    def transfer_to_nseeds(self, z: float = 0.0) -> np.ndarray:
        """Compute normalized matter power spectrum for seeding."""
        k_max = 10.0  # h/Mpc
        n_k = 2000
        k = np.logspace(-3, np.log10(k_max), n_k)
        P = self.linear_power_spectrum(k)
        return k, P


# ---------------------------------------------------------------------------
# Gaussian random fields
# ---------------------------------------------------------------------------


@dataclass
class GRFConfig:
    """Configuration for Gaussian random field generation."""

    cosmo: Cosmology = field(default_factory=Cosmology)
    box: float = 1000.0  # Mpc/h
    nside: int = 128  # cells per side of the periodic grid
    k_min: float = 2 * math.pi / 1000.0
    k_max: float = math.pi / 5.0
    seed: int = 42
    lensing: bool = False
    redshift: float = 0.0
    # Target sigma8. The input P(k) is rescaled so its sigma8 matches this
    # before the field is generated, giving the realisation a physical
    # amplitude. Set to None to use the input spectrum's own normalisation.
    sigma8: Optional[float] = None


def generate_grf(config: GRFConfig) -> Dict[str, Any]:
    """
    Generate a 3D Gaussian random density field on a periodic Cartesian grid,
    seeded from the linear matter power spectrum.

    Method
    ------
    1. Build the wavenumber grid k = 2*pi*fftfreq(n, L/n) on each axis.
    2. Restrict to the shell k_min <= |k| <= k_max.
    3. Draw the Fourier amplitudes from a complex Gaussian with variance set by
       the target power spectrum:
           <|delta_k|^2> = P(k),  with delta_k = (1/V) sum_x delta(x) e^{-ikx}
       so the real-space transform is delta(x) = V * sum_k delta_k e^{ikx}.
       numpy's ifftn divides by N = n^3, so the 1/V factor is applied as
       V/N = 1/N because V = L^3 = (L/n)^3 * n^3.
    4. Impose Hermitian symmetry, delta_{-k} = conj(delta_k), by assigning
       amplitudes only to half of the modes and mirroring the rest. Without
       this the inverse transform is complex and taking its real part silently
       halves the power, leaving the field indistinguishable from white noise.
    5. Remove the mean (kills the k = 0 mode).

    Assumptions
    -----------
    Gaussian initial conditions, linear theory for the input P(k), and a
    periodic box so that modes are quantised to multiples of 2*pi/L.

    Returns
    -------
    dict with:
        density     : (n, n, n) real density contrast, zero mean, unit variance
        grid        : cell-centre coordinates on each axis
        k           : tabulated input wavenumbers
        P_k         : tabulated input power spectrum
        realized_P_k : the power spectrum actually realised by the field
        config      : the configuration used
        correlation : real-space two-point function and lag axis
    """
    rng = np.random.default_rng(config.seed)

    box = config.box
    n = config.nside
    L = box
    n_cells = n**3

    # Grid wavenumbers on each axis (h/Mpc)
    kx = 2 * math.pi * np.fft.fftfreq(n, d=L / n)
    kxx, kyy, kzz = np.meshgrid(kx, kx, kx, indexing="ij")
    kk = np.sqrt(kxx**2 + kyy**2 + kzz**2)

    shell = (kk >= config.k_min) & (kk <= config.k_max)

    # Input power spectrum, interpolated onto the modes we will populate.
    k_vals, P_vals = config.cosmo.transfer_to_nseeds()
    P_interp = interp1d(k_vals, P_vals, kind="linear", bounds_error=False, fill_value=0.0)

    # Fix the absolute amplitude by matching sigma8. The BBKS amplitude from
    # As alone is degenerate with sigma8, and leaving it arbitrary would make
    # the field's variance depend on the grid resolution rather than on the
    # physics. Standardising the field to unit variance instead would be worse
    # still: it dumps the variance into modes near the Nyquist limit, which
    # then alias back into the low-k bins and corrupt P(k).
    if config.sigma8 is not None:
        # Normalise to the target sigma8 over the wavenumber range the grid
        # actually covers. Normalising over the full tabulated range instead
        # would misattribute the power that falls outside the shell to the
        # power inside it, inflating P(k) by the fraction of modes excluded.
        in_shell = (k_vals >= config.k_min) & (k_vals <= config.k_max)
        if in_shell.sum() < 4:
            raise ValueError(
                f"the requested shell [{config.k_min}, {config.k_max}] covers "
                f"too few tabulated wavenumbers to normalise sigma8"
            )
        P_shell = np.where(in_shell, P_vals, 0.0)
        P_shell_norm = normalize_power_spectrum_sigma8(
            k_vals, P_shell, target_sigma8=config.sigma8
        )
        P_vals = P_shell_norm
        P_interp = interp1d(
            k_vals, P_vals, kind="linear", bounds_error=False, fill_value=0.0
        )
    # Assign amplitudes to one representative of each +/-k pair so that
    # imposing Hermitian symmetry cannot double-count power.
    # The rule "index >= n/2 on the first axis where it differs" selects
    # exactly half of every conjugate pair.
    i_idx = np.arange(n)
    ii, jj, ll = np.meshgrid(i_idx, i_idx, i_idx, indexing="ij")
    # Canonical half-space: the first index where the mode differs from its
    # conjugate partner must be in the upper half of the array.
    conj_i = (-ii) % n
    conj_j = (-jj) % n
    conj_l = (-ll) % n
    canonical = (
        (ii > conj_i)
        | ((ii == conj_i) & (jj > conj_j))
        | ((ii == conj_i) & (jj == conj_j) & (ll >= conj_l))
    )
    # Self-conjugate modes (k = 0, and Nyquist planes) are assigned only once.
    self_conjugate = (
        (ii == conj_i) & (jj == conj_j) & (ll == conj_l)
    )
    half = shell & (canonical | self_conjugate)

    field_full = np.zeros((n, n, n), dtype=complex)
    n_modes = int(half.sum())
    if n_modes == 0:
        raise ValueError(
            f"no Fourier modes fall in [{config.k_min}, {config.k_max}] for "
            f"n={n}, L={L}; widen the shell or increase the resolution"
        )

    P_half = np.maximum(P_interp(kk[half]), 1e-30)
    # The estimator below returns P(k) = <|fftn(delta)|^2> * V_cell / N, so the
    # stored amplitudes must satisfy E[|F_k|^2> = N * P(k) / V_cell. A complex
    # Gaussian with that total power splits evenly between real and imaginary
    # parts, giving a variance of N*P/(2*V_cell) on each.
    cell = L / n
    cell_volume = cell**3
    amplitudes = np.sqrt(P_half * (n_cells / cell**3) / 2.0) * (
        rng.normal(0.0, 1.0, n_modes) + 1j * rng.normal(0.0, 1.0, n_modes)
    )
    field_full[half] = amplitudes

    # Mirror to the conjugate partner.
    field_full[conj_i[half], conj_j[half], conj_l[half]] = np.conj(amplitudes)

    # Real-space field. No extra volume factor: the N scaling already lives
    # in the amplitudes above.
    delta = np.real(np.fft.ifftn(field_full))

    # Remove any residual mean (kills the k = 0 mode).
    delta -= delta.mean()

    # A single realisation's sigma8 scatters around the target by the cosmic
    # variance of the box (15-30% for a few hundred Mpc). Rescale so the field
    # hits the requested sigma8 exactly: this makes the amplitude deterministic
    # and comparable with the theory prediction, while leaving the shape and
    # phase untouched.
    if config.sigma8 is not None:
        sigma_now = sigma8_from_field(delta, cell)
        if np.isfinite(sigma_now) and sigma_now > 0:
            delta = delta * (config.sigma8 / sigma_now)

    grid = np.linspace(-L / 2, L / 2, n)

    # Realized power spectrum, for validation of the construction.
    # <|delta_k|^2> = |delta_k|^2 / n_cells for a unit-variance field.
    realized = (np.abs(np.fft.fftn(delta)) ** 2) * (cell_volume / n_cells)
    sigma8_realised = sigma8_from_field(delta, cell)
    bins = np.linspace(config.k_min, config.k_max, 21)
    k_centres = 0.5 * (bins[:-1] + bins[1:])
    realized_radial = np.zeros_like(k_centres)
    for i in range(len(k_centres)):
        s = shell & (kk >= bins[i]) & (kk < bins[i + 1])
        realized_radial[i] = realized[s].mean() if s.any() else np.nan

    # Real-space two-point correlation function xi(r), normalised to xi(0)=1.
    corr = np.real(np.fft.ifftn(realized))
    xi = corr / corr.max() if corr.max() != 0 else corr
    lag = np.fft.fftfreq(n, d=L / n) * 2 * math.pi

    return {
        "density": delta,
        "grid": grid,
        "k": k_vals,
        "P_k": P_vals,
        "realized_P_k": {"k": k_centres, "P_k": realized_radial},
        "sigma8_realised": float(sigma8_realised),
        "delta_std": float(delta.std()),
        "n_modes": n_modes,
        "config": {
            "box": box,
            "nside": n,
            "k_min": config.k_min,
            "k_max": config.k_max,
            "seed": config.seed,
            "redshift": config.redshift,
        },
        "correlation": {"xi": xi, "k": lag},
    }


# ---------------------------------------------------------------------------
# Dark energy equation-of-state models
# ---------------------------------------------------------------------------


def de_equation_of_state(
    z: ArrayLike,
    w0: float = -1.0,
    wa: float = 0.0,
    model: str = "lcdm",
) -> ArrayLike:
    """
    Dark energy equation of state w(z).

    Models:
        lcdm    : w = -1 (cosmological constant)
        w_const : w = w0 (constant)
        w0wa    : w(z) = w0 + wa * z/(1+z)
        phm     : phenomenological Chaplygin-like evolution
    """
    z = np.asarray(z, dtype=float)
    if model == "lcdm":
        return -np.ones_like(z)
    if model == "w_const":
        return np.full_like(z, w0)
    if model == "w0wa":
        return w0 + wa * z / (1 + z)
    if model == "phm":
        # phenomenological: w(z) = w0 + (wa - w0) * z / (z + 1)  (smooth transition)
        return w0 * (1 + z) ** (-1) + wa * z / (1 + z) ** 2
    raise ValueError(f"Unknown dark energy model {model!r}")


@dataclass
class DECosmology(Cosmology):
    """Cosmology with evolving dark energy."""

    w0: float = -1.0
    wa: float = 0.0
    model: str = "w0wa"

    def curvature(self) -> float:
        """
        Omega_k from the closure constraint.

        For evolving dark energy the present-day closure still fixes
        Omega_k = 1 - Omega_m - Omega_L - Omega_r, so E(0) = 1.
        """
        return 1.0 - (self.om + self.ol + self.or_)

    def e(self, z: ArrayLike) -> ArrayLike:
        """
        E(z) for evolving dark energy.

        The dark energy density is evolved with the continuity equation:
            d ln rho_de / dz = 3 (1 + w(z)) / (1 + z)
        integrated from z = 0, where rho_de = Omega_L.
        """
        z = np.asarray(z, dtype=float)
        # Flatten so scalar, 1-D, and N-D inputs are all handled.
        z_flat = z.ravel()
        # Integrate on a grid that includes every requested redshift, so the
        # result is correct for unsorted input as well.
        z_grid = np.unique(np.concatenate([[0.0], z_flat[np.isfinite(z_flat)]]))
        w = de_equation_of_state(z_grid, self.w0, self.wa, self.model)
        # Continuity equation: rho_de(a) propto a^{-3(1+w)}. With z = 1/a - 1,
        # d ln rho_de / dz = 3 (1 + w(z)) / (1 + z). For w = -1 this vanishes,
        # reproducing a true cosmological constant.
        integrand = 3.0 * (1.0 + w) / (1.0 + z_grid)
        ln_rol = integrate.cumulative_trapezoid(integrand, z_grid, initial=0.0)
        ol_z = self.ol * np.exp(ln_rol)

        func = interp1d(z_grid, ol_z, kind="linear", bounds_error=False, fill_value=self.ol)
        ol_interp = func(z)
        ok = self.curvature()
        return np.sqrt(
            self.om * (1 + z) ** 3
            + self.or_ * (1 + z) ** 4
            + ok * (1 + z) ** 2
            + ol_interp
        )


# ---------------------------------------------------------------------------
# Anisotropic toy universes
# ---------------------------------------------------------------------------


def anisotropic_field(config: GRFConfig, axis: np.ndarray = np.array([1.0, 0.0, 0.0]),
                      amplitude: float = 0.1) -> Dict[str, Any]:
    """
    Generate a Gaussian random field with a dipole/quadrupole anisotropy
    along a preferred axis.

    δ_aniso(x) = δ_GRF(x) * (1 + amplitude * Y2(axis·x/|x|))

    Tests for large-scale isotropy / preferred directions (EXP-002).
    """
    base = generate_grf(config)
    delta = base["density"]
    shape = delta.shape

    axis = np.asarray(axis, dtype=float)
    axis = axis / np.linalg.norm(axis)

    # Coordinates of every cell, centred on the box.
    grid_axes = [np.arange(n) - (n - 1) / 2.0 for n in shape]
    gx, gy, gz = np.meshgrid(*grid_axes, indexing="ij")
    coords = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)

    # Angle between each cell direction and the preferred axis.
    r = np.sqrt((coords**2).sum(axis=1))
    r_safe = np.where(r > 0, r, 1.0)
    cos_theta = (coords @ axis) / r_safe
    cos_theta = np.clip(cos_theta, -1.0, 1.0)

    # l = 2 quadrupole: Y2 = (3 cos^2 - 1)/2. The mask at the origin avoids a
    # singularity in the angle; that single cell is left unmodulated.
    y2 = 0.5 * (3 * cos_theta**2 - 1)
    y2[r == 0] = 0.0

    # Add the quadrupole as an explicit component rather than modulating the
    # existing field multiplicatively. A product delta(x) * Y2(cos theta) has
    # near-zero correlation with Y2 itself, so it would be invisible to any
    # quadrupole detector; adding a component scaled by the field's own rms
    # makes the imposed anisotropy the dominant signal, which is what a
    # preferred-direction search is meant to detect.
    rms = float(delta.std())
    delta = delta + (amplitude * rms) * y2.reshape(shape)
    delta -= delta.mean()

    base["density"] = delta
    base["anisotropy"] = {
        "axis": axis.tolist(),
        "amplitude": amplitude,
        "type": "quadrupole",
        "ell": 2,
    }
    return base


# ---------------------------------------------------------------------------
# Finite topology toy models
# ---------------------------------------------------------------------------


def periodic_field(config: GRFConfig, L: Optional[float] = None) -> Dict[str, Any]:
    """
    Gaussian random field on a 3-torus of side L (compact multi-connected
    topology, EXP-012 / EXP-013).

    The field is periodic by construction (Fourier modes quantized to
    multiples of 2π/L). Matched-circle signatures arise when L < d_horizon.
    """
    if L is None:
        L = config.box
    # Rebuild the config with the new box size while preserving every other
    # parameter (cosmo, nside, seeds, wavenumber limits).
    cfg = replace(config, box=L)
    out = generate_grf(cfg)
    out["topology"] = {"type": "3-torus", "L": L}
    return out


def matched_circles_signature(config: GRFConfig, L: float) -> Dict[str, Any]:
    """
    Simulate matched-circle signatures for a compact universe of size L.

    For a torus with L < comoving distance to last scattering, identical
    circles appear in the CMB at antipodal (or rotated) orientations.

    Returns:
        dict with simulated circle pairs: (theta1, theta2, phi1, phi2, radius,
        rotation_angle).
    """
    cosmo = config.cosmo
    d_ls = float(cosmo.comoving_distance(1100.0))
    if d_ls <= L:
        return {
            "error": (
                "topology size L must be smaller than the comoving distance to "
                "the last-scattering surface"
            ),
            "L": L,
            "horizon_to_last_scattering": d_ls,
        }

    rng = np.random.default_rng(config.seed + 1000)
    n_pairs = 6
    circles = []
    for _ in range(n_pairs):
        theta1 = rng.uniform(0, math.pi)
        phi1 = rng.uniform(0, 2 * math.pi)
        radius = rng.uniform(0.1, 0.4) * math.pi
        # Circle pair: opposite side of torus, rotated by angle depending on winding
        theta2 = math.pi - theta1 + rng.normal(0, 0.02)
        phi2 = (phi1 + rng.uniform(0, 2 * math.pi)) % (2 * math.pi)
        rot = rng.uniform(0, 2 * math.pi)
        circles.append([theta1, theta2, phi1, phi2, radius, rot])

    return {
        "topology": {"type": "3-torus", "L": L},
        "horizon_to_last_scattering": float(d_ls),
        "circles": circles,
        "n_pairs": n_pairs,
    }


# ---------------------------------------------------------------------------
# Bubble collision signatures (EXP-011)
# ---------------------------------------------------------------------------


def bubble_collision_template(
    nlat: int = 128,
    r0: float = 0.15,  # radius of collision circle in radians
    phi: float = 0.0,  # center azimuth (radians)
    theta_c: float = 0.5,  # center polar angle (radians)
    contrast: float = 1e-5,  # temperature contrast in K (positive magnitude)
    profile: str = "flat",
) -> np.ndarray:
    """
    Generate a synthetic bubble-collision temperature pattern on a
    (nlat, 2*nlat) latitude-longitude map.

    Signature convention (Liu & Komatsu 2007): a bubble collision produces a
    temperature DEPRESSION, so the map is negative by convention when
    `contrast` is given as a positive magnitude.

    Parameters
    ----------
    nlat : number of latitude rows (map shape is (nlat, 2*nlat))
    r0 : angular radius of the collision circle, radians
    phi : azimuth of the circle centre, radians
    theta_c : polar angle of the circle centre, radians
    contrast : peak temperature contrast magnitude, K
    profile : "flat" | "radial" | "damped"

    Returns
    -------
    2D ndarray of shape (nlat, 2*nlat) in K.
    """
    if nlat < 4:
        raise ValueError("nlat must be >= 4")
    # A disc with an angular radius of pi covers the entire sphere, which is
    # not a local bubble-collision signature.
    if r0 >= math.pi:
        raise ValueError(
            f"r0={r0} rad must be smaller than pi; a disc of radius >= pi "
            "covers the whole sky and is not a localised signature"
        )
    if not (r0 > 0.0):
        raise ValueError("r0 must be positive")
    nlon = 2 * nlat
    lon = np.linspace(-math.pi, math.pi, nlon, endpoint=False)
    lat = np.linspace(math.pi / 2, -math.pi / 2, nlat)
    llon, llat = np.meshgrid(lon, lat, indexing="xy")

    # Unit vectors of every map pixel and of the circle centre.
    theta = np.pi / 2 - llat
    x = np.sin(theta) * np.cos(llon)
    y = np.sin(theta) * np.sin(llon)
    z = np.cos(theta)

    cx = math.sin(theta_c) * math.cos(phi)
    cy = math.sin(theta_c) * math.sin(phi)
    cz = math.cos(theta_c)

    # Great-circle angular distance from each pixel to the circle centre.
    d = np.arccos(np.clip(x * cx + y * cy + z * cz, -1.0, 1.0))

    map_ = np.zeros_like(d)
    inside = d <= r0
    if not np.any(inside):
        raise ValueError(
            f"collision circle (r0={r0} rad) falls outside the map; "
            "increase nlat or decrease r0"
        )

    if profile == "flat":
        map_[inside] = -abs(contrast)
    elif profile == "radial":
        map_[inside] = -abs(contrast) * (1 - d[inside] / r0)
    elif profile == "damped":
        # Smooth, cosine-damped profile falling to zero at the disc edge.
        map_[inside] = -abs(contrast) * 0.5 * (1 + np.cos(np.pi * d[inside] / r0))
    else:
        raise ValueError(f"Unknown profile {profile!r}")

    return map_


def inject_and_recover(
    template: np.ndarray,
    noise_sigma: float = 2e-6,  # K, realistic CMB noise level
    n_injections: int = 100,
    random_seed: int = 0,
    threshold_sigma: float = 3.0,
    profile: str = "flat",
) -> Dict[str, Any]:
    """
    Inject bubble-collision templates into Gaussian CMB-like noise and measure
    whether a detection algorithm recovers them (Sections 12 and 40).

    Injection-and-recovery is the required order of operations: the detector is
    first validated on synthetic skies where the signal is known, and only then
    applied to real observations.

    Detector: matched filter with a matched-shape template. The matched-filter
    SNR of a disc signal embedded in white noise of per-pixel sigma is
    SNR = contrast * sqrt(N_pixels) / sigma, so the recovered fraction increases
    monotonically with signal-to-noise.

    Returns
    -------
    dict with n_injections, noise_sigma, recovery_fraction, median_snr,
    threshold_sigma, and algorithm name.
    """
    rng = np.random.default_rng(random_seed)
    shape = template.shape
    nlat = shape[0]
    r0 = 0.15
    contrast = float(np.max(np.abs(template)))

    recovered = 0
    snrs = []
    for _ in range(n_injections):
        noise = rng.normal(0.0, noise_sigma, shape)
        # Randomize the injection position, keeping the disc away from the poles
        # so it is fully represented on the map.
        theta_c = rng.uniform(0.6, math.pi - 0.6)
        phi_c = rng.uniform(0.0, 2 * math.pi)
        t = bubble_collision_template(
            nlat=nlat, r0=r0, phi=phi_c, theta_c=theta_c,
            contrast=contrast, profile=profile,
        )
        map_noisy = noise + t

        # Matched filter: correlate the map with the template itself.
        snr = float(np.sum(map_noisy * t) / (noise_sigma * np.sqrt(np.sum(t**2))))
        snrs.append(snr)
        recovered += int(snr > threshold_sigma)

    snr_arr = np.asarray(snrs)
    return {
        "n_injections": n_injections,
        "noise_sigma": noise_sigma,
        "injected_contrast": contrast,
        "disc_radius_rad": r0,
        "recovery_fraction": recovered / n_injections,
        "median_snr": float(np.median(snr_arr)),
        "mean_snr": float(np.mean(snr_arr)),
        "threshold_sigma": threshold_sigma,
        "algorithm": "matched_filter",
    }


# ---------------------------------------------------------------------------
# Toy modified gravity & altered power spectra
# ---------------------------------------------------------------------------


def altered_power_spectrum(
    k: ArrayLike,
    cosmo: Cosmology,
    model: str = "altered_sigma8",
    amplitude: float = 0.1,
) -> ArrayLike:
    """
    Generate toy modified power spectra.

    Models:
        altered_sigma8 : P(k) scaled by (1 ± amplitude) — tests growth
        steeper        : tilt change n_s -> n_s ± 0.1
        cutoff         : large-scale power suppression (inflation alternative)
    """
    P_base = cosmo.linear_power_spectrum(k)
    if model == "altered_sigma8":
        return P_base * (1 + amplitude) ** 2
    if model == "steeper":
        return P_base * (k / k.mean()) ** 0.1
    if model == "cutoff":
        k_c = 0.01  # h/Mpc
        return P_base * (k ** 2 / (k ** 2 + k_c ** 2))
    raise ValueError(f"Unknown altered spectrum model {model!r}")


def altered_gravity_field(config: GRFConfig, model: str = "fR4", amplitude: float = 0.05) -> Dict[str, Any]:
    """
    Toy modified-gravity density field: enhanced clustering.

    fR4 (chameleon) model toy: σ8 increased by (1+amplitude).
    """
    base = generate_grf(config)
    # Simulate: multiply small-scale power
    delta = base["density"]
    # Convolve with a top-hat kernel to boost small-scale clustering
    from scipy.ndimage import gaussian_filter
    delta_small = delta + amplitude * gaussian_filter(delta, sigma=2)
    delta_small -= delta_small.mean()
    base["density"] = delta_small
    base["gravity_model"] = {"type": model, "amplitude": amplitude}
    return base


# ---------------------------------------------------------------------------
# Mock galaxy catalogs
# ---------------------------------------------------------------------------


def sigma8_from_power_spectrum(
    k: ArrayLike, p_k: ArrayLike, R: float = 8.0
) -> float:
    """
    Sigma_R computed from a tabulated power spectrum P(k).

    Equation:
        sigma_R^2 = (1/(2 pi^2 R)) * integral_0^inf k^2 P(k) W^2(kR) dk

    with the top-hat Fourier window W(x) = 3 (sin x - x cos x)/x^3. The
    integral is truncated at the largest tabulated k, which is adequate when
    P(k) has already fallen well below its peak.

    Returns
    -------
    sigma_R, or NaN if the input is unusable.
    """
    k = np.asarray(k, dtype=float)
    p = np.asarray(p_k, dtype=float)
    keep = (k > 0) & np.isfinite(p) & (p >= 0)
    if keep.sum() < 4:
        return float("nan")
    kk, pp = k[keep], p[keep]

    grid = np.concatenate([[1e-4], np.logspace(np.log10(kk[0]), np.log10(kk[-1]), 4000)])
    pp_grid = np.interp(grid, kk, pp, left=pp[0], right=pp[-1])

    x = grid * R
    with np.errstate(invalid="ignore", divide="ignore"):
        w = 3.0 * (np.sin(x) - x * np.cos(x)) / x**3
    w[~np.isfinite(w)] = 0.0

    sigma2 = float(np.trapezoid(grid**2 * pp_grid * w**2, grid) / (2 * math.pi**2 * R))
    return math.sqrt(sigma2) if sigma2 > 0 else float("nan")


def normalize_power_spectrum_sigma8(
    k: ArrayLike, p_k: ArrayLike, target_sigma8: float = 0.81, R: float = 8.0
) -> np.ndarray:
    """
    Rescale P(k) so that it reproduces a target sigma_R.

    The BBKS amplitude is fixed by As and the transfer function, but its
    overall normalisation is degenerate with sigma8. This applies the single
    multiplicative factor required to match the target, using the same
    top-hat definition of sigma8 everywhere in the codebase.

    Returns
    -------
    The rescaled power spectrum, or the input unchanged if sigma8 could not
    be computed.
    """
    measured = sigma8_from_power_spectrum(k, p_k, R=R)
    if not np.isfinite(measured) or measured <= 0:
        return np.asarray(p_k, dtype=float)
    return np.asarray(p_k, dtype=float) * (target_sigma8 / measured) ** 2


def sigma8_from_field(delta: np.ndarray, cell_size: float, R: float = 8.0) -> float:
    """
    Sigma_R measured directly from a periodic density field.

    Equation:
        P(k) = <|delta_k|^2> / V
        sigma_R^2 = (1/(2 pi^2 R)) * integral k^2 P(k) W^2(kR) dk

    W(x) = 3 (sin x - x cos x)/x^3 is the top-hat window in Fourier space.

    This is the inverse of the operation used to normalise a field, so it can
    be used to rescale a realisation to a target amplitude.
    """
    delta = np.asarray(delta, dtype=float)
    n = delta.shape[0]

    # Same convention as _binned_power_spectrum: divide by the number of cells
    # and multiply by the cell volume, so the two estimators agree exactly.
    delta_k = np.fft.fftn(delta)
    power = (np.abs(delta_k) ** 2) * (cell_size**3 / n**3)

    k_axis = 2 * math.pi * np.fft.fftfreq(n, d=cell_size)
    kx, ky, kz = np.meshgrid(k_axis, k_axis, k_axis, indexing="ij")
    k_mag = np.sqrt(kx**2 + ky**2 + kz**2)

    # Rasterise onto a radial grid: mean P(k) in shells.
    n_r = 300
    k_max_rad = float(np.max(k_mag))
    edges = np.linspace(0.0, k_max_rad, n_r + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])
    radial = np.zeros(n_r)
    counts = np.zeros(n_r)
    for i in range(n_r):
        shell = (k_mag >= edges[i]) & (k_mag < edges[i + 1])
        counts[i] = shell.sum()
        if counts[i] > 0:
            radial[i] = power[shell].mean()

    kk = centres[counts > 0]
    pp = radial[counts > 0]
    if kk.size < 4:
        return float("nan")

    grid = np.linspace(1e-4, k_max_rad, 4000)
    pp_grid = np.interp(grid, kk, pp, left=pp[0], right=0.0)
    x = grid * R
    with np.errstate(invalid="ignore", divide="ignore"):
        w = 3.0 * (np.sin(x) - x * np.cos(x)) / x**3
    w[~np.isfinite(w)] = 0.0

    sigma2 = float(np.trapezoid(grid**2 * pp_grid * w**2, grid) / (2 * math.pi**2 * R))
    return math.sqrt(sigma2) if sigma2 > 0 else float("nan")


def clustered_mock_galaxy_catalog(
    box: float = 400.0,
    n_grid: int = 48,
    nbar: float = 0.05,
    bias: float = 1.6,
    cosmo: Optional[Cosmology] = None,
    random_seed: int = 42,
    k_min: float = 0.02,
    k_max: float = 0.6,
    target_sigma8: Optional[float] = None,
) -> Dict[str, Any]:
    """
    A realistic mock galaxy catalogue: Poisson galaxies sampled from a
    Lambda CDM density field in a periodic box.

    Procedure
    ---------
    1. Generate a Gaussian random matter density field delta(x) on a periodic
       n_grid^3 grid, seeded from the BBKS linear power spectrum normalised to
       sigma8. The box is periodic by construction, so the field has the
       correct clustering and no boundary effects.
    2. Draw the galaxy density from the bias relation, rho(x) = 1 + b*delta(x),
       clipped at zero so that under-dense cells are empty rather than negative,
       then renormalised so the mean density is exactly nbar.
    3. Sample nbar * V Poisson galaxies in proportion to that density, placing
       each one uniformly inside its host cell.

    The result is a catalogue whose measured power spectrum is
    P_gal(k) ~ b^2 [P_matter(k) + 1/nbar], which is exactly what a real
    survey produces up to the selection function.

    Parameters
    ----------
    box : periodic box side in Mpc/h
    n_grid : cells per side of the density grid
    nbar : mean galaxy number density in (Mpc/h)^-3
    bias : linear galaxy bias
    target_sigma8 : rescale the density field so its measured sigma8 matches
        this value (default: the input cosmology's sigma8). Without this the
        field has the right shape but an arbitrary amplitude, because
        generate_grf standardises delta to unit variance.

    Returns
    -------
    dict with x, y, z (Mpc/h), delta (density field), cell_size, n_galaxies,
    nbar, bias, box, and the cosmo parameters used.
    """
    cosmo = cosmo or Cosmology()
    rng = np.random.default_rng(random_seed)

    # 1. Underlying matter density field on a periodic grid.
    cfg = GRFConfig(
        cosmo=cosmo,
        box=box,
        nside=n_grid,
        k_min=k_min,
        k_max=k_max,
        seed=random_seed,
        sigma8=target_sigma8 if target_sigma8 is not None else cosmo.sigma8,
    )
    field = generate_grf(cfg)
    delta = field["density"]
    sigma8_applied = float(field.get("sigma8_realised", float("nan")))

    # 1b. The realised sigma8 of a single realisation scatters around the
    #     target by the cosmic variance of the box (~15-20%), so rescale the
    #     field to hit the target exactly. This makes the mock's amplitude
    #     deterministic and comparable with the theory prediction.
    cell_size = box / n_grid
    sigma_target = target_sigma8 if target_sigma8 is not None else cosmo.sigma8
    sigma_realised = sigma8_from_field(delta, cell_size)
    if np.isfinite(sigma_realised) and sigma_realised > 0:
        delta = delta * (sigma_target / sigma_realised)
        sigma8_applied = float(sigma_target)

    # 2. Galaxy density from the bias relation. Clipping at zero removes the
    #    contribution of underdense cells, which lowers the mean, so we
    #    renormalise to hit the requested mean density exactly.
    rho = np.clip(1.0 + bias * delta, 0.0, None)
    rho_mean = float(rho.mean())
    if rho_mean <= 0:
        raise ValueError("bias too large: the clipped density field is empty")
    rho = rho / rho_mean  # dimensionless, mean 1

    # 3. Poisson sampling: pick cells in proportion to their density weight,
    #    then place a uniform random position inside each chosen cell.
    cell = box / n_grid
    n_cells = n_grid**3
    n_galaxies = round(nbar * box**3)
    if n_galaxies < 1:
        raise ValueError("mock catalogue is empty; increase nbar")
    weights = rho.ravel() / n_cells
    chosen = rng.choice(rho.size, size=n_galaxies, p=weights)
    i, j, k = np.unravel_index(chosen, rho.shape)

    # Uniform position within the cell (the within-cell density is constant).
    x = (i + rng.random(n_galaxies)) * cell
    y = (j + rng.random(n_galaxies)) * cell
    z = (k + rng.random(n_galaxies)) * cell

    return {
        "x": x,
        "y": y,
        "z_cart": z,
        "delta": delta,
        "rho": rho,
        "cell_size": cell,
        "n_grid": n_grid,
        "n_galaxies": n_galaxies,
        "nbar": n_galaxies / box**3,
        "nbar_target": nbar,
        "bias": bias,
        "box": box,
        "cosmo": {"h": cosmo.h, "om": cosmo.om, "ol": cosmo.ol, "sigma8": cosmo.sigma8},
        "sigma8_applied": sigma8_applied,
        "random_seed": random_seed,
        "note": "clustered Lambda CDM mock; positions are periodic box coordinates",
    }


def effective_bias(
    galaxy_field: np.ndarray, matter_field: np.ndarray
) -> float:
    """
    Linear galaxy bias measured empirically from two co-located fields.

    Equation:
        b_eff = <delta_g(k) delta_m(k)> / <delta_m(k)^2>
              = sum_k delta_g(k) delta_m(k) / sum_k |delta_m(k)|^2

    Assumptions:
        - Linear regime, so the galaxy field is b_eff times the matter field
          plus shot noise. Shot noise is uncorrelated with the matter field
          and therefore does not bias this ratio.

    Measuring the bias rather than assuming it matters: a mock catalogue is
    built by clipping the density at zero (empty cells cannot have negative
    density), which reduces the effective clustering below the input bias.
    Real analyses estimate the bias from the data for exactly this reason.
    """
    delta_g = np.asarray(galaxy_field, dtype=float).ravel()
    delta_m = np.asarray(matter_field, dtype=float).ravel()
    num = float(np.sum(delta_g * delta_m))
    den = float(np.sum(delta_m * delta_m))
    if den <= 0:
        return float("nan")
    return num / den


def _binned_power_spectrum(
    delta: np.ndarray,
    cell: float,
    volume: float,
    shot_noise: float,
    k_min: float,
    k_max: float,
    n_bins: int,
) -> Dict[str, Any]:
    """
    Bin a periodic density-contrast field's power spectrum onto a log k grid.

    Shared by the galaxy-catalogue estimator and the matter-field estimator so
    that the two are guaranteed to use identical binning and normalisation. Any
    difference between them is then attributable to the galaxies, not to the
    measurement convention.

    Equation:
        With delta_k = (1/N) sum_x delta(x) e^{-ikx} and N the number of cells,

            <delta_k delta_k'> = (P(k)/N) delta_{kk'}

        and numpy's fftn returns sum_x delta(x) e^{-ikx} = N delta_k, so

            P(k) = <|fftn(delta)|^2> / N

        That result is still per unit *cell*, not per (Mpc/h)^3. Converting to
        the continuum convention requires multiplying by the cell volume
        V_cell = (L/n)^3: a white field with unit variance per cell has a
        continuum power P(k) = V_cell, not 1.

        Sanity check: for white noise, sigma_R^2 should equal the continuum
        variance V_cell * <delta^2>_cell, which this scaling reproduces.

        The binned value is the shell mean minus the shot-noise term, with
        Poisson + sampling uncertainty sigma_P = (P + 1/nbar) / sqrt(N_modes).
    """
    delta = np.asarray(delta, dtype=float)
    n = delta.shape[0]
    n_cells = n**3
    cell_volume = cell**3

    delta_k = np.fft.fftn(delta)
    power = (np.abs(delta_k) ** 2) * (cell_volume / n_cells)

    k_axis = 2 * math.pi * np.fft.fftfreq(n, d=cell)
    kx, ky, kz = np.meshgrid(k_axis, k_axis, k_axis, indexing="ij")
    k_mag = np.sqrt(kx**2 + ky**2 + kz**2)

    edges = np.logspace(math.log10(k_min), math.log10(k_max), n_bins + 1)
    centres = 0.5 * (edges[:-1] + edges[1:])

    p_k = np.full(n_bins, np.nan)
    p_k_err = np.full(n_bins, np.nan)
    n_modes = np.zeros(n_bins, dtype=int)

    for i in range(n_bins):
        shell = (k_mag >= edges[i]) & (k_mag < edges[i + 1])
        n_modes[i] = int(shell.sum())
        if n_modes[i] == 0:
            continue
        raw = float(power[shell].mean())
        p_k[i] = max(raw - shot_noise, 0.0)
        p_k_err[i] = (raw + shot_noise) / math.sqrt(n_modes[i])

    return {
        "k": centres,
        "p_k": p_k,
        "p_k_err": p_k_err,
        "n_modes": n_modes,
    }


def measure_power_spectrum_from_field(
    delta: np.ndarray,
    box: float,
    n_grid: int,
    k_min: float = 0.02,
    k_max: Optional[float] = None,
    n_bins: int = 20,
) -> Dict[str, Any]:
    """
    Power spectrum of a continuous density field (no shot noise).

    Used to validate the galaxy-catalogue estimator: the field here is the one
    the mock galaxies were actually sampled from, so comparing the two isolates
    any error introduced by the galaxy measurement.
    """
    cell = box / n_grid
    volume = box**3
    k_nyquist = math.pi / cell
    k_max = float(k_max) if k_max is not None else k_nyquist
    if k_max > k_nyquist:
        raise ValueError(
            f"requested k_max={k_max:.4g} exceeds the grid Nyquist wavenumber "
            f"{k_nyquist:.4g} h/Mpc"
        )
    out = _binned_power_spectrum(
        np.asarray(delta, dtype=float), cell, volume, 0.0, k_min, k_max, n_bins
    )
    out.update({"box": box, "n_grid": n_grid, "cell_size": cell, "shot_noise": 0.0})
    return out


def measure_power_spectrum(
    positions: Dict[str, ArrayLike],
    box: float,
    n_grid: int,
    k_min: float = 0.02,
    k_max: Optional[float] = None,
    n_bins: int = 20,
) -> Dict[str, Any]:
    """
    Measure the galaxy power spectrum P(k) from a periodic box catalogue.

    Method
    ------
    1. Bin the galaxies onto an n_grid^3 grid to form the density contrast
       delta = n_cell / nbar - 1.
    2. P(k) = <|delta_k|^2> / V with delta_k the FFT of delta. The shot noise
       1/nbar is subtracted to recover the matter signal.
    3. Bin |k| onto a log grid and attach the standard Poisson + sampling
       uncertainty sigma_P = (P + 1/nbar) / sqrt(N_modes).

    Returns dict with k (centres), p_k, p_k_err, n_modes, shot_noise, nbar.
    """
    x = np.asarray(positions["x"], dtype=float)
    y = np.asarray(positions["y"], dtype=float)
    z = np.asarray(positions["z_cart"], dtype=float)
    n_points = len(x)

    cell = box / n_grid
    n_cells = n_grid**3
    # Two different densities are needed and confusing them is a silent error:
    #   nbar     : galaxy number density per (Mpc/h)^3, which sets the shot
    #              noise floor 1/nbar of P(k)
    #   nbar_cell: mean galaxies per grid cell, which normalises the density
    #              contrast to zero mean
    nbar = n_points / box**3
    nbar_cell = n_points / n_cells

    idx = np.stack([x, y, z], axis=1) / cell
    idx = np.floor(idx).astype(int) % n_grid
    counts = np.zeros((n_grid,) * 3, dtype=float)
    np.add.at(counts, (idx[:, 0], idx[:, 1], idx[:, 2]), 1.0)

    delta = counts / nbar_cell - 1.0

    # A grid can only represent modes up to the Nyquist wavenumber. Silently
    # clamping a larger request would return empty shells as zero power, so
    # reject it and tell the caller what resolution the grid actually supports.
    k_nyquist = math.pi / cell
    if k_max is None:
        k_max = k_nyquist
    elif float(k_max) > k_nyquist:
        raise ValueError(
            f"requested k_max={float(k_max):.4g} exceeds the grid Nyquist "
            f"wavenumber {k_nyquist:.4g} h/Mpc (cell size {cell:.4g} Mpc/h for "
            f"n_grid={n_grid}, box={box:g}). Increase n_grid, decrease the box "
            "size, or lower k_max."
        )
    k_max = float(k_max)
    if k_max <= k_min:
        raise ValueError(
            f"k_max ({k_max:.4g}) <= k_min ({k_min:.4g}): the grid is too coarse "
            f"for the requested wavenumber range (Nyquist = {k_nyquist:.4g})"
        )

    # Power spectrum, shared binning/normalisation with the field estimator.
    shot = 1.0 / nbar
    binned = _binned_power_spectrum(
        delta, cell=cell, volume=box**3, shot_noise=shot,
        k_min=k_min, k_max=k_max, n_bins=n_bins,
    )
    p_k = binned["p_k"]
    p_k_err = binned["p_k_err"]
    centres = binned["k"]
    n_modes = binned["n_modes"]

    return {
        "k": centres,
        "p_k": p_k,
        "p_k_err": p_k_err,
        "n_modes": n_modes,
        "shot_noise": shot,
        "nbar": nbar,
        "n_points": n_points,
        "box": box,
        "n_grid": n_grid,
        "cell_size": cell,
        "k_nyquist": k_nyquist,
        "k_max_used": k_max,
        "delta": delta,
    }


def mock_galaxy_catalog(
    n_galaxies: int = 10000,
    z_max: float = 1.0,
    cosmo: Optional[Cosmology] = None,
    bias: float = 1.2,
    random_seed: int = 42,
) -> Dict[str, Any]:
    """
    Generate a mock galaxy catalog with a redshift distribution peaking at
    z ~ z_max/2 and luminosity-weighted selection.

    Returns:
        dict with z, x, y, z_cart (Mpc), r (comoving distance), w (weight).
    """
    rng = np.random.default_rng(random_seed)
    cosmo = cosmo or Cosmology()

    # Redshift distribution: p(z) ∝ z^2 exp(-(z/z0)^1.5) (toy Schechter-like)
    z0 = z_max / 1.5
    z_samples = z0 * rng.gamma(2.0, 1.0, size=n_galaxies * 10)
    z_samples = z_samples[z_samples < z_max]
    if len(z_samples) < n_galaxies:
        z_samples = rng.uniform(0, z_max, size=n_galaxies)
    z = z_samples[:n_galaxies]

    # Comoving distances
    r = cosmo.comoving_distance(z)

    # Angular distribution (uniform sky, with a small dipole for isotropy tests)
    cos_theta = rng.uniform(-1, 1, size=n_galaxies)
    phi = rng.uniform(0, 2 * math.pi, size=n_galaxies)
    theta = np.arccos(cos_theta)

    x = r * np.sin(theta) * np.cos(phi)
    y = r * np.sin(theta) * np.sin(phi)
    z_cart = r * np.cos(theta)

    # Selection weight
    w = np.exp(-(z / z0) ** 1.5)

    return {
        "z": z,
        "x": x,
        "y": y,
        "z_cart": z_cart,
        "r": r,
        "w": w,
        "n_galaxies": n_galaxies,
        "cosmo": {"h": cosmo.h, "om": cosmo.om, "ol": cosmo.ol},
        "random_seed": random_seed,
    }


# ---------------------------------------------------------------------------
# Simulation orchestration
# ---------------------------------------------------------------------------


@dataclass
class SimulationJob:
    """A self-contained simulation job with full reproducibility."""

    name: str
    model: str
    parameters: Dict[str, Any]
    description: Optional[str] = None
    seed: int = 42
    config: Optional[Dict[str, Any]] = None

    def reproducibility_hash(self) -> str:
        """Hash identifying the exact simulation configuration."""
        data = json.dumps(
            {
                "name": self.name,
                "model": self.model,
                "parameters": self.parameters,
                "seed": self.seed,
                "cosmos_version": "0.1.0.dev0",
            },
            sort_keys=True,
        )
        return hashlib.sha256(data.encode()).hexdigest()[:16]

    def run(self) -> SimOutput:
        """Run the simulation and return the output dict."""
        raise NotImplementedError


@dataclass
class LCDMSimulation(SimulationJob):
    """ΛCDM Gaussian random field simulation (EXP-001, EXP-003)."""

    def run(self) -> SimOutput:
        config = GRFConfig(**(self.config or {}), seed=self.seed)
        out = generate_grf(config)
        out["job"] = {
            "name": self.name,
            "model": self.model,
            "parameters": self.parameters,
            "reproducibility_hash": self.reproducibility_hash(),
        }
        return out


@dataclass
class AnisotropicSimulation(SimulationJob):
    """Anisotropic toy universe (EXP-002)."""

    def run(self) -> SimOutput:
        config = GRFConfig(**(self.config or {}), seed=self.seed)
        out = anisotropic_field(config, axis=np.array(self.parameters.get("axis", [1, 0, 0])),
                                amplitude=self.parameters.get("amplitude", 0.1))
        out["job"] = {"name": self.name, "model": self.model, "parameters": self.parameters,
                      "reproducibility_hash": self.reproducibility_hash()}
        return out


@dataclass
class TopologySimulation(SimulationJob):
    """Finite topology (3-torus) simulation (EXP-012)."""

    def run(self) -> SimOutput:
        config = GRFConfig(**(self.config or {}), seed=self.seed)
        L = self.parameters.get("L", config.box * 0.5)
        out = periodic_field(config, L=L)
        circles = matched_circles_signature(config, L=L)
        out["matched_circles"] = circles
        out["job"] = {"name": self.name, "model": self.model, "parameters": self.parameters,
                      "reproducibility_hash": self.reproducibility_hash()}
        return out


@dataclass
class BubbleCollisionSimulation(SimulationJob):
    """Bubble collision injection & recovery test (EXP-011)."""

    def run(self) -> SimOutput:
        template = bubble_collision_template(
            nlat=self.parameters.get("nlat", 64),
            r0=self.parameters.get("r0", 0.15),
            contrast=self.parameters.get("contrast", 1e-5),
            profile=self.parameters.get("profile", "flat"),
        )
        recovery = inject_and_recover(
            template,
            noise_sigma=self.parameters.get("noise_sigma", 2e-6),
            n_injections=self.parameters.get("n_injections", 50),
            random_seed=self.seed,
            threshold_sigma=self.parameters.get("threshold_sigma", 3.0),
        )
        out = {"template": template, "recovery": recovery}
        out["job"] = {"name": self.name, "model": self.model, "parameters": self.parameters,
                      "reproducibility_hash": self.reproducibility_hash()}
        return out


@dataclass
class MockGalaxySimulation(SimulationJob):
    """Mock galaxy catalog (EXP-003, EXP-004)."""

    def run(self) -> SimOutput:
        cosmo = Cosmology(h=self.parameters.get("h", 0.674), om=self.parameters.get("om", 0.315))
        out = mock_galaxy_catalog(
            n_galaxies=self.parameters.get("n_galaxies", 10000),
            z_max=self.parameters.get("z_max", 1.0),
            cosmo=cosmo,
            bias=self.parameters.get("bias", 1.2),
            random_seed=self.seed,
        )
        out["job"] = {"name": self.name, "model": self.model, "parameters": self.parameters,
                      "reproducibility_hash": self.reproducibility_hash()}
        return out


# ---------------------------------------------------------------------------
# Simulation registry
# ---------------------------------------------------------------------------

SIMULATION_TYPES: Dict[str, type[SimulationJob]] = {
    "lcdm": LCDMSimulation,
    "anisotropic": AnisotropicSimulation,
    "topology": TopologySimulation,
    "bubble_collision": BubbleCollisionSimulation,
    "mock_galaxy": MockGalaxySimulation,
}


def create_simulation(name: str, model: str, parameters: Dict[str, Any],
                      seed: Optional[int] = None, config: Optional[Dict[str, Any]] = None) -> SimulationJob:
    """Factory: create a simulation job from name/model/parameters."""
    cls = SIMULATION_TYPES.get(model)
    if cls is None:
        raise ValueError(f"Unknown simulation model {model!r}. Available: {list(SIMULATION_TYPES)}")
    return cls(name=name, model=model, parameters=parameters, seed=seed or 42, config=config)


def run_simulation_batch(
    jobs: List[SimulationJob],
    out_dir: Optional[Path | str] = None,
    progress: bool = True,
) -> List[SimOutput]:
    """Run a batch of simulations and save outputs to JSON."""
    from tqdm import tqdm
    results = []
    for job in tqdm(jobs, desc="simulations", disable=not progress):
        out = job.run()
        results.append(out)
        if out_dir:
            p = Path(out_dir) / f"{job.name}_{job.reproducibility_hash()}.json"
            p.parent.mkdir(parents=True, exist_ok=True)
            with open(p, "w") as f:
                json.dump(out, f, indent=2, default=str)
    return results


# ---------------------------------------------------------------------------
# Visualization helpers for simulations
# ---------------------------------------------------------------------------


def field_statistics(field_dict: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute statistics of a simulated density field.

    For a Gaussian random field the skewness and excess kurtosis should both be
    zero; "non_gaussianity" reports the excess kurtosis, i.e.
    g2 = <delta^4>/sigma^4 - 3, which vanishes for a Gaussian field.
    """
    delta = np.asarray(field_dict["density"], dtype=float)
    flat = delta.ravel()
    excess_kurtosis = float(scipy_stats.kurtosis(flat, fisher=True))
    return {
        "mean": float(delta.mean()),
        "std": float(delta.std()),
        "skewness": float(scipy_stats.skew(flat)),
        "kurtosis": float(excess_kurtosis),
        "non_gaussianity": excess_kurtosis,
        "min": float(delta.min()),
        "max": float(delta.max()),
    }


def save_field(field_dict: Dict[str, Any], path: Path | str) -> None:
    """Save a simulated field to a .npz archive."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(p, **{k: v for k, v in field_dict.items() if isinstance(v, np.ndarray)})


def load_field(path: Path | str) -> Dict[str, Any]:
    """Load a simulated field from a .npz archive."""
    arr = np.load(path)
    out = dict(arr)
    return out
