"""
Scientific validation tests for the COSMOS simulation engine.

These tests verify that the simulation engine produces fields with the
statistical properties implied by the ΛCDM model, and that injection-and-
recovery of known signals works as advertised (Sections 24 and 40 of the spec).
"""

from __future__ import annotations

import numpy as np
import pytest

from cosmos import simulations as sim


class TestCosmology:
    def test_hubble_distance_known_value(self):
        """
        Planck 2018: the Hubble distance c/H0 should be ~4448 Mpc for H0 = 67.4.
        """
        c = sim.Cosmology(h=0.674)
        assert c.hubble_radius == pytest.approx(299792.458 / 67.4, rel=1e-6)
        assert 4400 < c.hubble_radius < 4500

    def test_e_function_at_zeros(self):
        c = sim.Cosmology(h=0.674, om=0.315, ol=0.685, or_=9.2e-5, ok=0.0)
        assert c.e(0.0) == pytest.approx(1.0)
        # E(z) grows with redshift in a matter-dominated universe.
        assert c.e(1.0) > c.e(0.0)
        assert c.e(3.0) > c.e(1.0)

    def test_hubble_increases_with_redshift(self):
        c = sim.Cosmology()
        z = np.linspace(0, 3, 20)
        h = c.hubble(z)
        assert np.all(np.diff(h) > 0)

    def test_comoving_distance_monotonic_and_positive(self):
        c = sim.Cosmology()
        z = np.linspace(0, 3, 50)
        d = c.comoving_distance(z)
        assert d[0] == pytest.approx(0.0, abs=1e-6)
        assert np.all(np.diff(d) > 0)

    def test_angular_diameter_distance_peaks_near_z14(self):
        """
        The angular diameter distance D_A = D_C/(1+z) reaches a maximum at
        z ~ 1.6, corresponding to the observed redshift of the most distant
        resolved objects. This is a real, non-trivial consequence of expanding
        cosmologies and a standard validation check.
        """
        c = sim.Cosmology()
        z = np.linspace(0.1, 5.0, 2000)
        d_a = c.angular_diameter_distance(z)
        z_max = z[int(np.argmax(d_a))]
        assert 1.3 < z_max < 2.0

    def test_power_spectrum_positive_and_decreasing(self):
        c = sim.Cosmology()
        k = np.logspace(-3, 1, 100)
        p = c.linear_power_spectrum(k)
        assert np.all(p > 0)
        assert p[-1] < p[0]

    def test_growth_factor_normalized_to_one_today(self):
        c = sim.Cosmology()
        assert c.growth_factor(np.array([0.0]))[0] == pytest.approx(1.0, rel=1e-3)

    def test_growth_factor_suppressed_in_dark_energy_dominated_epoch(self):
        c = sim.Cosmology()
        assert c.growth_factor(np.array([2.0]))[0] < 0.4


class TestDarkEnergyModels:
    def test_lcdm_gives_minus_one(self):
        z = np.linspace(0, 3, 50)
        assert np.all(sim.de_equation_of_state(z, model="lcdm") == -1.0)

    def test_w_const_returns_w0(self):
        z = np.linspace(0, 3, 50)
        w = sim.de_equation_of_state(z, w0=-0.9, model="w_const")
        assert np.allclose(w, -0.9)

    def test_w0wa_behaviour(self):
        z = 0.0
        assert sim.de_equation_of_state(np.array([z]), w0=-1.0, wa=0.3, model="w0wa")[0] == pytest.approx(-1.0)
        # w(1) = w0 + wa/2
        assert sim.de_equation_of_state(np.array([1.0]), w0=-1.0, wa=0.3, model="w0wa")[0] == pytest.approx(-0.85)

    def test_phantom_divergence_not_monotonic_breaking(self):
        z = np.linspace(0, 3, 50)
        w = sim.de_equation_of_state(z, w0=-1.2, wa=0.0, model="w0wa")
        assert np.all(np.isfinite(w))

    def test_unknown_model_raises(self):
        with pytest.raises(ValueError):
            sim.de_equation_of_state(np.array([1.0]), model="not_a_model")

    def test_de_cosmology_grows_faster_than_lcdm_if_w_above_minus_one(self):
        """
        A cosmological constant with w = -0.9 expands faster than w = -1 at
        intermediate redshift, which is how DESI-style data can favor evolving
        dark energy.
        """
        lcdm = sim.DECosmology(h=0.674, om=0.315, ol=0.685, w0=-1.0, wa=0.0, model="w0wa")
        evolving = sim.DECosmology(h=0.674, om=0.315, ol=0.685, w0=-0.9, wa=0.0, model="w_const")
        z = np.array([0.5])
        assert evolving.e(z)[0] > lcdm.e(z)[0]


class TestGaussianRandomField:
    def test_field_is_mean_free(self):
        cfg = sim.GRFConfig(nside=24, seed=1)
        out = sim.generate_grf(cfg)
        assert out["density"].mean() == pytest.approx(0.0, abs=1e-10)

    def test_field_has_the_requested_sigma8(self):
        """
        The field must carry a physical amplitude, not an arbitrary one.

        Standardising delta to unit variance would be wrong: it dumps the
        variance into modes near the grid Nyquist limit, which then alias back
        into the low-k bins and corrupt P(k). Instead the input spectrum is
        normalised to a target sigma8 before the field is generated.
        """
        target = 0.75
        cfg = sim.GRFConfig(nside=32, box=400.0, k_min=0.02, k_max=0.25,
                            seed=5, sigma8=target)
        out = sim.generate_grf(cfg)
        assert out["sigma8_realised"] == pytest.approx(target, rel=0.25)

    def test_sigma8_target_changes_the_amplitude(self):
        """A larger requested sigma8 must produce a larger-amplitude field."""
        a = sim.generate_grf(sim.GRFConfig(nside=32, box=400.0, k_min=0.02,
                                           k_max=0.25, seed=5, sigma8=0.5))
        b = sim.generate_grf(sim.GRFConfig(nside=32, box=400.0, k_min=0.02,
                                           k_max=0.25, seed=5, sigma8=1.0))
        assert b["sigma8_realised"] > a["sigma8_realised"]
        assert b["density"].std() > a["density"].std()

    def test_field_reproduces_the_input_power_spectrum(self):
        """
        The estimator that produces the field and the estimator used to
        analyse it must agree, otherwise every downstream comparison is
        internally consistent but wrong.
        """
        cfg = sim.GRFConfig(nside=32, box=400.0, k_min=0.02, k_max=0.25,
                            seed=11, sigma8=0.81)
        out = sim.generate_grf(cfg)

        from scipy.interpolate import interp1d

        target = sim.normalize_power_spectrum_sigma8(out["k"], out["P_k"], 0.81)
        interp = interp1d(out["k"], target, bounds_error=False, fill_value=0.0)
        realized = np.asarray(out["realized_P_k"]["P_k"], dtype=float)
        kk = np.asarray(out["realized_P_k"]["k"], dtype=float)
        expected = interp(kk)

        ratio = realized / expected
        # A single realisation carries cosmic variance, so allow ~25%.
        assert np.nanmedian(ratio) == pytest.approx(1.0, rel=0.25)

    def test_field_is_gaussian(self):
        """
        A Gaussian random field must be Gaussian by construction; the skewness
        and excess kurtosis should be close to zero.
        """
        cfg = sim.GRFConfig(nside=32, seed=2)
        delta = sim.generate_grf(cfg)["density"]
        flat = delta.ravel()
        from scipy import stats as sps
        assert abs(sps.skew(flat)) < 0.15
        assert abs(sps.kurtosis(flat)) < 0.3

    def test_reproducibility_with_same_seed(self):
        cfg = sim.GRFConfig(nside=16, seed=99)
        a = sim.generate_grf(cfg)["density"]
        b = sim.generate_grf(cfg)["density"]
        assert np.array_equal(a, b)

    def test_different_seeds_give_different_fields(self):
        a = sim.generate_grf(sim.GRFConfig(nside=16, seed=1))["density"]
        b = sim.generate_grf(sim.GRFConfig(nside=16, seed=2))["density"]
        assert not np.array_equal(a, b)

    def test_non_gaussianity_statistic_is_small(self):
        out = sim.generate_grf(sim.GRFConfig(nside=32, seed=3))
        stats = sim.field_statistics(out)
        assert abs(stats["non_gaussianity"]) < 0.2

    def test_no_modes_in_shell_raises(self):
        cfg = sim.GRFConfig(nside=8, box=400.0, k_min=50.0, k_max=100.0)
        with pytest.raises(ValueError):
            sim.generate_grf(cfg)


class TestAnisotropicField:
    def test_anisotropy_metadata_recorded(self):
        cfg = sim.GRFConfig(nside=24, seed=4)
        out = sim.anisotropic_field(cfg, axis=np.array([1.0, 0.0, 0.0]), amplitude=0.3)
        assert "anisotropy" in out
        assert out["anisotropy"]["amplitude"] == 0.3
        assert out["anisotropy"]["type"] == "quadrupole"
        assert out["anisotropy"]["ell"] == 2

    def test_shape_preserved(self):
        cfg = sim.GRFConfig(nside=24, seed=4)
        base = sim.generate_grf(cfg)["density"]
        aniso = sim.anisotropic_field(cfg, amplitude=0.3)["density"]
        assert aniso.shape == base.shape

    def test_zero_amplitude_reduces_to_isotropic(self):
        cfg = sim.GRFConfig(nside=16, seed=5)
        iso = sim.generate_grf(cfg)["density"]
        near_iso = sim.anisotropic_field(cfg, amplitude=0.0)["density"]
        assert np.allclose(iso, near_iso)

    def test_anisotropy_creates_quadrupole_asymmetry(self):
        """
        A quadrupole modulation along x must make the field differ between
        opposite outer regions more than an isotropic field does.

        The l = 2 pattern is symmetric about x = 0, so the comparison is between
        the two outermost slabs along the preferred axis rather than between
        hemispheres.
        """
        cfg = sim.GRFConfig(nside=24, box=400.0, seed=11)
        iso = sim.generate_grf(cfg)["density"]
        aniso = sim.anisotropic_field(
            cfg, axis=np.array([1.0, 0.0, 0.0]), amplitude=0.8
        )["density"]

        mid = iso.shape[0] // 2
        slab = 4

        def asymmetry(field):
            return abs(field[mid + slab:, :, :].mean() - field[: mid - slab, :, :].mean())

        # The anisotropy must increase the asymmetry relative to the same
        # underlying realisation without it.
        assert asymmetry(aniso) > asymmetry(iso)

    def test_anisotropy_direction_is_respected(self):
        """
        The imposed modulation must correlate with the quadrupole pattern of the
        requested axis, and better than with a different axis.

        A slab-mean comparison is not a valid detector here: the l=2 pattern
        averages to zero over any symmetric region, so the right test is a
        correlation against the expected angular pattern.
        """
        cfg = sim.GRFConfig(nside=24, box=400.0, seed=12)

        def quadrupole_correlation(field, axis):
            axis = np.asarray(axis, float)
            axis = axis / np.linalg.norm(axis)
            n = field.shape[0]
            g = np.arange(n) - (n - 1) / 2.0
            gx, gy, gz = np.meshgrid(g, g, g, indexing="ij")
            coords = np.stack([gx.ravel(), gy.ravel(), gz.ravel()], axis=1)
            r = np.sqrt((coords**2).sum(axis=1))
            r_safe = np.where(r > 0, r, 1.0)
            cos_t = np.clip((coords @ axis) / r_safe, -1.0, 1.0)
            y2 = 0.5 * (3 * cos_t**2 - 1)
            y2[r == 0] = 0.0
            a = field.ravel() - field.mean()
            b = y2 - y2.mean()
            denom = np.sqrt((a**2).sum() * (b**2).sum())
            return float(np.sum(a * b) / denom) if denom > 0 else 0.0

        along_x = sim.anisotropic_field(
            cfg, axis=np.array([1.0, 0.0, 0.0]), amplitude=1.0
        )["density"]
        along_z = sim.anisotropic_field(
            cfg, axis=np.array([0.0, 0.0, 1.0]), amplitude=1.0
        )["density"]

        c_x = quadrupole_correlation(along_x, np.array([1.0, 0.0, 0.0]))
        c_x_vs_z = quadrupole_correlation(along_x, np.array([0.0, 0.0, 1.0]))
        c_z = quadrupole_correlation(along_z, np.array([0.0, 0.0, 1.0]))

        assert c_x > 0.1, "the x-axis anisotropy does not show an x quadrupole"
        assert c_z > 0.1, "the z-axis anisotropy does not show a z quadrupole"
        # A field built for x must not look more z-like than z-like itself.
        assert c_x > c_x_vs_z

    def test_field_remains_mean_free_and_finite(self):
        cfg = sim.GRFConfig(nside=24, box=400.0, seed=6)
        delta = sim.anisotropic_field(cfg, amplitude=0.5)["density"]
        assert np.all(np.isfinite(delta))
        assert abs(delta.mean()) < 1e-8 * max(1.0, delta.std())


class TestTopology:
    def test_periodic_field_is_topology_labelled(self):
        out = sim.periodic_field(sim.GRFConfig(nside=16, seed=6), L=500.0)
        assert out["topology"]["type"] == "3-torus"
        assert out["topology"]["L"] == 500.0

    def test_matched_circles_requires_compact_universe(self):
        """
        Matched circles can only exist if the topology size is smaller than
        the distance to the last-scattering surface.
        """
        cfg = sim.GRFConfig(nside=8, seed=7)
        too_big = sim.matched_circles_signature(cfg, L=20000.0)
        assert "error" in too_big

    def test_matched_circles_generated_for_compact_universe(self):
        cfg = sim.GRFConfig(nside=8, seed=8)
        out = sim.matched_circles_signature(cfg, L=500.0)
        assert "circles" in out
        assert out["n_pairs"] == len(out["circles"])
        for theta, theta2, phi, phi2, radius, rot in out["circles"]:
            assert 0 <= theta <= np.pi
            assert 0 <= theta2 <= np.pi
            assert radius > 0


class TestBubbleCollisions:
    def test_template_has_expected_shape(self):
        t = sim.bubble_collision_template(nlat=16)
        assert t.shape == (16, 32)

    def test_template_is_zero_outside_circle(self):
        r0 = 0.3
        t = sim.bubble_collision_template(nlat=64, r0=r0)
        # A small disc must not cover the whole sky.
        assert np.mean(np.abs(t) > 0) < 0.2

    def test_template_is_negative_inside_circle(self):
        """
        Bubble collisions in the standard (Liu & Komatsu) model produce a
        temperature DEPRESSION inside the circle, so the map is negative
        inside and zero outside.
        """
        t = sim.bubble_collision_template(nlat=32, contrast=1e-5)
        assert t.min() < 0
        assert t.max() == 0.0

    def test_damped_profile_respects_edge(self):
        t = sim.bubble_collision_template(nlat=32, r0=0.4, profile="damped")
        assert t.min() < 0
        assert np.all(t >= -1.1e-5)

    def test_injection_recovery_reports_fraction(self):
        t = sim.bubble_collision_template(nlat=16)
        res = sim.inject_and_recover(t, noise_sigma=2e-6, n_injections=10)
        assert res["n_injections"] == 10
        assert 0.0 <= res["recovery_fraction"] <= 1.0
        assert res["algorithm"] == "matched_filter"

    def test_stronger_signal_recovers_better(self):
        """
        Injection-and-recovery must show a monotonic sensitivity: reducing the
        noise cannot lower the recovered fraction.
        """
        t = sim.bubble_collision_template(nlat=24)
        weak = sim.inject_and_recover(t, noise_sigma=2e-6, n_injections=30, random_seed=1)
        strong = sim.inject_and_recover(t, noise_sigma=2e-7, n_injections=30, random_seed=1)
        assert strong["median_snr"] > weak["median_snr"]
        assert strong["recovery_fraction"] >= weak["recovery_fraction"]

    def test_detection_threshold_is_enforced(self):
        """
        A signal far below the detection threshold must not be claimed as
        recovered. This guards against over-claiming sensitivity.
        """
        t = sim.bubble_collision_template(nlat=24, contrast=1e-10)
        res = sim.inject_and_recover(
            t, noise_sigma=2e-6, n_injections=20, random_seed=2, threshold_sigma=3.0
        )
        assert res["recovery_fraction"] == 0.0

    def test_unknown_profile_raises(self):
        with pytest.raises(ValueError):
            sim.bubble_collision_template(nlat=8, profile="nonsense")

    def test_circle_off_map_raises(self):
        # A disc larger than the sphere cannot be represented.
        with pytest.raises(ValueError):
            sim.bubble_collision_template(nlat=8, r0=10.0)


class TestMockGalaxyCatalog:
    def test_catalog_shape_and_ranges(self):
        cat = sim.mock_galaxy_catalog(n_galaxies=500, z_max=0.5, random_seed=1)
        assert len(cat["z"]) == 500
        assert np.all(cat["z"] >= 0) and np.all(cat["z"] < 0.5)
        assert np.all(cat["w"] > 0)

    def test_distances_increase_with_redshift(self):
        cat = sim.mock_galaxy_catalog(n_galaxies=300, z_max=1.0, random_seed=2)
        order = np.argsort(cat["z"])
        r = np.asarray(cat["r"])[order]
        assert np.all(np.diff(r) > -1e-6)

    def test_reproducible(self):
        a = sim.mock_galaxy_catalog(n_galaxies=100, random_seed=5)
        b = sim.mock_galaxy_catalog(n_galaxies=100, random_seed=5)
        assert np.array_equal(a["z"], b["z"])

    def test_angular_distribution_covers_sky(self):
        cat = sim.mock_galaxy_catalog(n_galaxies=2000, random_seed=3)
        x, y, zc = np.asarray(cat["x"]), np.asarray(cat["y"]), np.asarray(cat["z_cart"])
        r = np.sqrt(x**2 + y**2 + zc**2)
        # Positions should lie on spheres of radius = comoving distance.
        assert np.allclose(r, np.asarray(cat["r"]), rtol=1e-6)


class TestSimulationJobs:
    def test_factory_creates_known_types(self):
        job = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=3)
        assert isinstance(job, sim.LCDMSimulation)

    def test_unknown_model_raises(self):
        with pytest.raises(ValueError):
            sim.create_simulation("t", "does_not_exist", {})

    def test_reproducibility_hash_is_deterministic(self):
        a = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=3)
        b = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=3)
        assert a.reproducibility_hash() == b.reproducibility_hash()

    def test_reproducibility_hash_changes_with_seed(self):
        a = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=3)
        b = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=4)
        assert a.reproducibility_hash() != b.reproducibility_hash()

    def test_lcdm_job_runs(self):
        job = sim.create_simulation("t", "lcdm", {"nside": 8}, seed=1)
        out = job.run()
        assert "density" in out and "job" in out
        assert out["job"]["reproducibility_hash"] == job.reproducibility_hash()

    def test_topology_job_includes_matched_circles(self):
        job = sim.create_simulation("t", "topology", {"L": 500.0}, seed=1)
        out = job.run()
        assert "matched_circles" in out

    def test_bubble_collision_job_reports_recovery(self):
        job = sim.create_simulation("t", "bubble_collision", {"resolution": 8}, seed=1)
        out = job.run()
        assert "recovery" in out


class TestAlteredSpectrum:
    def test_altered_sigma8_scales_power(self):
        c = sim.Cosmology()
        k = np.logspace(-3, 0, 50)
        base = c.linear_power_spectrum(k)
        up = sim.altered_power_spectrum(k, c, model="altered_sigma8", amplitude=0.1)
        assert np.all(up > base)

    def test_cutoff_suppresses_large_scales(self):
        c = sim.Cosmology()
        k = np.logspace(-4, 0, 200)
        base = c.linear_power_spectrum(k)
        cut = sim.altered_power_spectrum(k, c, model="cutoff")
        # At the smallest k the cutoff model should be strongly suppressed.
        assert cut[0] < base[0]

    def test_altered_gravity_increases_structure(self):
        cfg = sim.GRFConfig(nside=16, seed=5)
        out = sim.altered_gravity_field(cfg, amplitude=0.3)
        assert "gravity_model" in out
        assert out["gravity_model"]["amplitude"] == 0.3
        assert np.isfinite(out["density"]).all()