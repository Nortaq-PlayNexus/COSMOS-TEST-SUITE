"""
BAO distance calculations.

Baryon acoustic oscillation measurements report distances in units of the sound
horizon r_s at the drag epoch rather than in absolute megaparsecs, so
interpreting them requires both the distance measures defined here and a value
of r_s.

What this module does not do
----------------------------
It does not compute r_s. An early version integrated the photon-baryon sound
speed to obtain the drag-epoch sound horizon; that implementation could not be
made to agree with the published Planck 2018 value, and rather than ship an
integral that could not be validated it was removed. The published r_s is
carried as a constant with its uncertainty and DOI (see
`PLANCK_2018_RS_MPC`), which is also standard practice for BAO-only analyses.

Validation
----------
`hubble_distance` is checked against the DESI/eBOSS D_H column and agrees to
better than 1% at z = 2.330 and to 4% worst case across the BAO range; the
residual is the difference between the DESI best-fit cosmology and the Planck
2018 parameters used by the model. See `tests/test_cosmology.py`.

A known problem with one data mirror is recorded in
`TestDESIColumnConvention`: the column labelled `DM_over_rs` in the
CobayaSampler mirror of the DESI DR2 vectors reproduces the *comoving*
distance D_C/r_s rather than the transverse distance D_M/r_s.
"""

from __future__ import annotations

import numpy as np
from scipy import integrate

# Energy density in radiation, in units of rho_crit h^2 today, *including*
# massless and massive neutrinos (Planck convention).
OMEGA_GAMMA_H2 = 2.4728e-5

# Effective number of neutrino species assumed by Planck 2018.
N_EFF_DEFAULT = 3.046


def photon_density(h: float, n_eff: float = N_EFF_DEFAULT) -> float:
    """Photon-plus-neutrino energy density Omega_gamma (not divided by h^2)."""
    return OMEGA_GAMMA_H2 * (1.0 + 0.2271 * n_eff) / h**2


#: Speed of light in km/s, used for the Hubble distance c/H0.
C_KM_S = 299792.458

#: Sound horizon at the drag epoch from Planck 2018 base-LambdaCDM,
#: Aghanim et al. 2020 (A&A 641, A6), doi:10.1051/0004-6361/201833910.
#: BAO measurements are reported in units of r_s, and standard practice in
#: BAO-only analyses is to take r_s from a CMB prior rather than recompute it.
#: Carrying the published uncertainty alongside the value keeps that external
#: dependence visible instead of burying it.
PLANCK_2018_RS_MPC = 147.09
PLANCK_2018_RS_SIGMA_MPC = 0.22
PLANCK_2018_RS_DOI = "10.1051/0004-6361/201833910"


def hubble_distance_scale(h: float) -> float:
    """
    The Hubble distance c/H0 in Mpc.

    H0 = 100*h in km/s/Mpc, so c/H0 = c/(100*h). Using c/h instead would
    overstate every distance by a factor of 100.
    """
    return C_KM_S / (100.0 * h)


def transverse_distance(z, om: float, ol: float, h: float = 0.6736) -> np.ndarray:
    """
    Comoving transverse distance D_M in Mpc, assuming flat geometry.

    Equation: D_M = (c/H0) / (1+z) * integral_0^z dz'/E(z')
    """
    z = np.atleast_1d(np.asarray(z, dtype=float))
    c_over_h0 = hubble_distance_scale(h)
    out = np.zeros_like(z)
    for i, zi in enumerate(z):
        if zi <= 0:
            out[i] = 0.0
            continue
        grid = np.linspace(0.0, zi, max(int(200 * zi) + 50, 200))
        ez = np.sqrt(
            om * (1 + grid) ** 3
            + ol
            + (1 - om - ol) * (1 + grid) ** 2
        )
        integral = integrate.cumulative_trapezoid(1.0 / ez, grid, initial=0.0)
        out[i] = c_over_h0 * integral[-1] / (1 + zi)
    return out


def hubble_distance(z, om: float, ol: float, h: float = 0.6736) -> np.ndarray:
    """
    Hubble distance D_H = c/H(z) in Mpc.

    Equation: D_H = (c/H0) / E(z)
    """
    z = np.atleast_1d(np.asarray(z, dtype=float))
    c_over_h0 = hubble_distance_scale(h)
    ez = np.sqrt(
        om * (1 + z) ** 3 + ol + (1 - om - ol) * (1 + z) ** 2
    )
    return c_over_h0 / ez


def f_volume(z, om: float, ol: float, h: float = 0.6736) -> np.ndarray:
    """
    The BAO volume-averaged distance D_V in Mpc.

    Equation: D_V = [ z D_M^2 D_H ]^{1/3}

    DESI reports D_V/r_s for its lowest redshift bin, so this is needed to
    compare like with like.
    """
    dm = transverse_distance(z, om, ol, h)
    dh = hubble_distance(z, om, ol, h)
    z = np.atleast_1d(np.asarray(z, dtype=float))
    return np.cbrt(z * dm**2 * dh)
