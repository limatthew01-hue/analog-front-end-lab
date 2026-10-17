import subprocess
import sys
import tempfile
import unittest

import numpy as np

from src.front_end import Config, quantize, ratio_db, sine_response, tolerance_sweep, transfer, waveforms


class FilterTests(unittest.TestCase):
    def setUp(self):
        self.cfg = Config()

    def test_cutoff_units(self):
        self.assertAlmostEqual(self.cfg.cutoff_hz, 1591.5494309189535)

    def test_dc_gain(self):
        self.assertEqual(transfer(0, 10_000, 10e-9), 1)

    def test_cutoff_gain_and_phase(self):
        h = transfer(self.cfg.cutoff_hz, 10_000, 10e-9)
        self.assertAlmostEqual(abs(h), 1/np.sqrt(2))
        self.assertAlmostEqual(np.angle(h, deg=True), -45)

    def test_high_frequency_rolloff(self):
        values = transfer(np.array([10, 100])*self.cfg.cutoff_hz, 10_000, 10e-9)
        self.assertAlmostEqual(20*np.log10(abs(values[1]/values[0])), -20, delta=.05)

    def test_loading_changes_dc_gain(self):
        self.assertAlmostEqual(transfer(0, 10_000, 10e-9, 100_000).real, 10/11)

    def test_loading_changes_time_constant(self):
        effective_r = 1/(1/10_000 + 1/100_000)
        loaded_fc = 1/(2*np.pi*effective_r*10e-9)
        h = transfer(loaded_fc, 10_000, 10e-9, 100_000)
        self.assertAlmostEqual(abs(h), (10/11)/np.sqrt(2))

    def test_sine_starts_at_initial_capacitor_voltage(self):
        self.assertAlmostEqual(sine_response(np.array([0]), .1, 100, 10_000, 10e-9)[0], 0)

    def test_response_satisfies_rc_differential_equation(self):
        t = np.linspace(.001, .005, 100_001)
        v = sine_response(t, .1, 100, 10_000, 10e-9)
        derivative = np.gradient(v, t)
        residual = 1e-4*derivative + v - .1*np.sin(2*np.pi*100*t)
        self.assertLess(np.max(abs(residual[2:-2])), 1e-8)

    def test_invalid_components_frequencies_and_configuration(self):
        for args in [(100, 0, 10e-9), (100, 10_000, -1e-9), (-1, 10_000, 10e-9)]:
            with self.assertRaises(ValueError): transfer(*args)
        for changes in [dict(r_ohm=0), dict(c_farad=float('nan')), dict(sample_hz=40_000),
                        dict(adc_bits=0), dict(c_tolerance=1), dict(measure_after_s=.04)]:
            with self.subTest(changes=changes):
                with self.assertRaises(ValueError): Config(**changes)


class ADCTests(unittest.TestCase):
    def test_lsb_uses_4096_bins(self):
        self.assertAlmostEqual(Config().lsb_v, .0008056640625)

    def test_endpoint_codes_and_clipping_flags(self):
        q = Config().lsb_v
        codes, voltage, clipped = quantize([0, q-1e-12, q, 3.3-1e-12, 3.3, -.1, 4])
        np.testing.assert_array_equal(codes, [0, 0, 1, 4095, 4095, 0, 4095])
        np.testing.assert_array_equal(clipped, [False, False, False, False, True, True, True])
        self.assertAlmostEqual(voltage[0], q/2)

    def test_nonclipped_error_within_half_lsb(self):
        samples = np.linspace(.01, 3.29, 19_773)
        _, reconstructed, clipped = quantize(samples)
        self.assertFalse(clipped.any())
        self.assertLessEqual(np.max(abs(reconstructed-samples)), Config().lsb_v/2 + 1e-15)

    def test_invalid_adc_inputs(self):
        for samples, bits, reference in [([np.nan], 12, 3.3), ([1], 0, 3.3), ([1], 12, 0), ([1], 12, np.nan)]:
            with self.assertRaises(ValueError): quantize(samples, bits, reference)


class ExperimentTests(unittest.TestCase):
    def test_tolerance_reproducibility(self):
        first = tolerance_sweep(Config(), 1000, 7)
        second = tolerance_sweep(Config(), 1000, 7)
        for a, b in zip(first, second): np.testing.assert_array_equal(a, b)

    def test_tolerance_samples_stay_inside_physical_corners(self):
        cfg = Config()
        _, _, f = tolerance_sweep(cfg, 10_000, 7)
        low = cfg.cutoff_hz/(1.01*1.05)
        high = cfg.cutoff_hz/(.99*.95)
        self.assertTrue(np.all(f >= low) and np.all(f <= high))

    def test_zero_tolerance_collapses_to_nominal(self):
        cfg = Config(r_tolerance=0, c_tolerance=0)
        _, _, f = tolerance_sweep(cfg, 10, 7)
        np.testing.assert_allclose(f, cfg.cutoff_hz)

    def test_waveform_headroom_and_adc_codes(self):
        t, vin, vout, codes, adc, clipped, *_ = waveforms(Config())
        self.assertEqual(len(t), 6000)
        self.assertTrue(np.all((codes >= 0) & (codes <= 4095)))
        self.assertFalse(clipped.any())
        self.assertAlmostEqual(vout[0], 1.65)

    def test_tone_ratio_matches_frequency_domain(self):
        cfg = Config()
        t, _, _, _, _, _, signal, interference, clean, unwanted = waveforms(cfg)
        m = t >= .01
        expected = 20*np.log10((cfg.signal_peak_v/cfg.interference_peak_v)
                    * abs(transfer(cfg.signal_hz, cfg.r_ohm, cfg.c_farad))
                    / abs(transfer(cfg.interference_hz, cfg.r_ohm, cfg.c_farad)))
        self.assertAlmostEqual(ratio_db(clean[m], unwanted[m]), expected, places=8)
        self.assertAlmostEqual(ratio_db(signal[m], interference[m]), 20*np.log10(2.5))

    def test_cli_rejects_negative_resistance(self):
        with tempfile.TemporaryDirectory() as folder:
            result = subprocess.run([sys.executable, 'src/front_end.py', '--r-ohm', '-1', '--out', folder],
                                    capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('positive', result.stderr)


if __name__ == '__main__':
    unittest.main()
