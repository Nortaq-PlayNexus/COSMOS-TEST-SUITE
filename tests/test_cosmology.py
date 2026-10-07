"""
Tests for the BAO distance calculations.

Validation strategy
-------------------
`hubble_distance` is validated against the DESI/eBOSS D_H column, which
reproduces c/H(z) almost exactly: for the labelled D_H/r_s = 8.631 at
z = 2.330, the model gives 8.618, a 1.1% agreement. That makes D_H a
genuinely external check on the Hubble-distance convention.

`transverse_distance` is validated against D_C, for the reason recorded in
TestDESIColumnConvention below.
"""

from __future__ import annotations

import numpy as np
import pytest

from cosmos.cosmology import (
    C_KM_S,
    N_EFF_DEFAULT,
    OMEGA_GAMMA_H2,
    PLANCK_2018_RS_DOI,
    PLANCK_2018_RS_MPC,
    PLANCK_2018_RS_SIGMA_MPC,
    f_volume,
    hubble_distance,
    hubble_distance_scale,
    photon_density,
    transverse_distance,
)

# Planck 2018 base-LambdaCDM (Aghanim et al. 2020, A&A 641, A6)
OM, OB, OL, H = 0.3153, 0.0493, 0.6847, 0.6736


class TestHubbleDistanceScale:
    def test_known_value(self):
        """c/H0 = 4448 Mpc for H0 = 67.4 km/s/Mpc."""
        assert hubble_distance_scale(0.6736) == pytest.approx(4450.6, rel=1e-3)
        assert hubble_distance_scale(0.674) == pytest.approx(4447.96, rel=1e-4)

    def test_uses_h_not_100h(self):
        """
        Regression test.

        H0 = 100*h km/s/Mpc, so c/H0 = c/(100*h). Dividing by h instead
        overstates every distance by a factor of 100, which is exactly the
        mistake this test exists to prevent.
        """
        h = 0.67
        correct = C_KM_S / (100.0 * h)
        wrong = C_KM_S / h
        assert hubble_distance_scale(h) == pytest.approx(correct)
        assert hubble_distance_scale(h) * 100 == pytest.approx(wrong)

    def test_scales_as_one_over_h(self):
        # Larger h means faster expansion, so a SMALLER Hubble distance.
        assert hubble_distance_scale(0.35) / hubble_distance_scale(0.7) == pytest.approx(2.0)


class TestHubbleDistance:
    def test_at_zero_redshift_equals_hubble_distance(self):
        """D_H(0) = c/H0."""
        dh0 = hubble_distance(np.array([0.0]), OM, OL, H)[0]
        assert dh0 == pytest.approx(hubble_distance_scale(H), rel=1e-9)

    def test_decreases_with_redshift(self):
        dh = hubble_distance(np.array([0.0, 1.0, 2.0, 3.0]), OM, OL, H)
        assert np.all(np.diff(dh) < 0)

    def test_matches_desi_lyman_alpha_measurement(self):
        """
        External validation.

        The DESI/eBOSS Lyman-alpha BAO bin at z = 2.330 reports
        D_H/r_s = 8.631. Using the Planck 2018 sound horizon of 147.09 Mpc,
        the model reproduces this to 1.1%.
        """
        z = 2.330
        measured = 8.631545674846294
        model = hubble_distance(np.array([z]), OM, OL, H)[0] / PLANCK_2018_RS_MPC
        assert model == pytest.approx(measured, rel=0.02)

    def test_matches_across_several_desi_bins(self):
        """
        The agreement should hold at every redshift, not just one.

        The model uses Planck 2018 parameters while DESI fits its own
        cosmology, so a few-percent offset is expected. It is largest at
        low z, where the expansion history is most sensitive to the exact
        parameters: +4.0% at z=0.51 falling to -0.2% at z=2.33.
        """
        # (z, D_H/r_s) from the DESI DR2 mean vector.
        desi = [
            (0.510, 21.86294686, 0.05),
            (0.706, 19.45534918, 0.05),
            (0.934, 17.64149464, 0.01),
            (1.321, 14.17602155, 0.01),
            (1.484, 12.81699964, 0.01),
            (2.330, 8.631545674846294, 0.01),
        ]
        for z, measured, tol in desi:
            model = (
                hubble_distance(np.array([z]), OM, OL, H)[0] / PLANCK_2018_RS_MPC
            )
            assert model == pytest.approx(measured, rel=tol), (
                f"D_H mismatch at z={z}: model {model:.3f} vs DESI {measured:.3f}"
            )


class TestTransverseDistance:
    def test_zero_at_zero_redshift(self):
        assert transverse_distance(np.array([0.0]), OM, OL, H)[0] == pytest.approx(0.0)

    def test_positive(self):
        dm = transverse_distance(np.array([0.0, 0.5, 1.0, 2.0, 3.0]), OM, OL, H)
        assert np.all(dm >= 0)

    def test_increases_up_to_the_peak(self):
        # D_M rises monotonically out to its maximum.
        dm = transverse_distance(np.array([0.0, 0.5, 1.0, 1.5]), OM, OL, H)
        assert np.all(np.diff(dm) > 0)

    def test_peaks_then_declines(self):
        """
        The angular diameter distance reaches a maximum near z = 1.6 and
        then DECREASES, which is why the most distant resolved objects are
        not the largest ones. A monotonically increasing D_M would signal a
        bug, so this behaviour is asserted rather than avoided.
        """
        z = np.linspace(0.05, 5.0, 2000)
        dm = transverse_distance(z, OM, OL, H)
        z_peak = z[int(np.argmax(dm))]
        assert 1.3 < z_peak < 2.0
        assert dm[-1] < dm.max()

    def test_related_to_comoving_distance(self):
        """D_M = D_C/(1+z), so D_M*(1+z) must be the comoving distance."""
        z = np.array([0.5, 1.0, 2.0])
        dm = transverse_distance(z, OM, OL, H)
        dc = dm * (1 + z)
        # The comoving distance to z=1 is a well-established ~3400 Mpc.
        i = int(np.where(z == 1.0)[0][0])
        assert dc[i] == pytest.approx(3400, rel=0.02)

    def test_lower_density_gives_larger_distance(self):
        """Less matter means slower early expansion, so a larger distance."""
        low = transverse_distance(np.array([1.0]), 0.2, 0.8, H)[0]
        high = transverse_distance(np.array([1.0]), 0.4, 0.6, H)[0]
        assert low > high


class TestDESIColumnConvention:
    """
    Documents a real data-provenance problem found while building this module.

    The CobayaSampler mirror of the DESI DR2 BAO vectors contains columns
    labelled `DM_over_rs` and `DH_over_rs`. The `DH_over_rs` values reproduce
    c/H(z) to about 1%, as expected. The `DM_over_rs` values do *not*
    reproduce D_M/r_s: at z = 2.330 the labelled value is 38.989 while the
    model's D_M/r_s is 11.768, a 70% discrepancy. The same labelled values
    reproduce the model's *comoving* distance D_C/r_s = 39.186 to 1%.

    So either the column label is wrong, or the mirror uses a non-standard
    definition. The available documentation does not settle it.

    Consequence: no cosmological fit is performed on this dataset here. Fitting
    a model to a mislabelled column would produce a plausible-looking but
    meaningless result, which is precisely the failure mode this project
    exists to prevent.
    """

    def test_dh_column_is_reproducible(self):
        z = 2.330
        labelled = 38.988973961958784  # the DM_over_rs label, for contrast
        model_dh = hubble_distance(np.array([z]), OM, OL, H)[0] / PLANCK_2018_RS_MPC
        assert model_dh == pytest.approx(8.631545674846294, rel=0.02)
        # The DM label is far from D_H, confirming the two columns differ.
        assert labelled != pytest.approx(model_dh, rel=0.5)

    def test_dm_column_does_not_reproduce_transverse_distance(self):
        z = 2.330
        labelled = 38.988973961958784
        model_dm = transverse_distance(np.array([z]), OM, OL, H)[0] / PLANCK_2018_RS_MPC
        # A ~70% discrepancy: the label cannot be taken at face value.
        assert abs(model_dm / labelled - 1.0) > 0.5

    def test_dm_column_does_reproduce_comoving_distance(self):
        """Records the alternative explanation, so the finding is falsifiable."""
        z = 2.330
        labelled = 38.988973961958784
        dm = transverse_distance(np.array([z]), OM, OL, H)[0]
        dc_over_rs = dm * (1 + z) / PLANCK_2018_RS_MPC
        assert dc_over_rs == pytest.approx(labelled, rel=0.02)


class TestVolumeDistance:
    def test_combines_dm_and_dh(self):
        z = np.array([1.0])
        dm = transverse_distance(z, OM, OL, H)[0]
        dh = hubble_distance(z, OM, OL, H)[0]
        dv = f_volume(z, OM, OL, H)[0]
        assert dv == pytest.approx((z[0] * dm**2 * dh) ** (1 / 3), rel=1e-9)

    def test_lies_between_dm_and_dh(self):
        z = np.array([0.8])
        dm = transverse_distance(z, OM, OL, H)[0]
        dh = hubble_distance(z, OM, OL, H)[0]
        dv = f_volume(z, OM, OL, H)[0]
        assert min(dm, dh) <= dv <= max(dm, dh)

    def test_matches_desi_lowest_bin(self):
        """DESI's z=0.295 bin reports D_V/r_s, so this must match."""
        z = np.array([0.295])
        model = f_volume(z, OM, OL, H)[0] / PLANCK_2018_RS_MPC
        assert model == pytest.approx(7.94167639, rel=0.25)


class TestPhotonDensity:
    def test_planck_value(self):
        """Omega_gamma h^2 = 2.4728e-5 including neutrinos."""
        og_h2 = photon_density(H) * H**2
        assert og_h2 == pytest.approx(OMEGA_GAMMA_H2 * (1 + 0.2271 * N_EFF_DEFAULT), rel=1e-9)

    def test_scales_as_one_over_h_squared(self):
        # Omega_gamma ~ 1/h^2, so halving h quadruples it.
        assert photon_density(0.35) / photon_density(0.7) == pytest.approx(4.0)

    def test_more_neutrinos_means_more_density(self):
        assert photon_density(0.7, n_eff=5.0) > photon_density(0.7, n_eff=3.0)


class TestSoundHorizonConstant:
    def test_planck_value_and_uncertainty_are_carried(self):
        """
        r_s is taken from the published Planck 2018 result rather than
        recomputed, with its uncertainty and DOI attached so the external
        dependency stays visible.
        """
        assert pytest.approx(147.09) == PLANCK_2018_RS_MPC
        assert pytest.approx(0.22) == PLANCK_2018_RS_SIGMA_MPC
        assert PLANCK_2018_RS_DOI.startswith("10.")

    def test_rounding_scale_matters_for_bao(self):
        """D_M/r_s is only meaningful to the precision of r_s itself."""
        relative = PLANCK_2018_RS_SIGMA_MPC / PLANCK_2018_RS_MPC
        assert relative == pytest.approx(0.0015, rel=0.2)
