import unittest
import numpy as np
from sensor_ml import (FEATURES, FS, LABELS, LSB, Rules, SAMPLES, features, make_dataset,
                       models, scores, split_devices, waveform)


class SignalTests(unittest.TestCase):
    def test_waveform_reproducibility(self):
        np.testing.assert_array_equal(waveform(7, 1, 0, 0), waveform(7, 1, 0, 0))
        self.assertFalse(np.array_equal(waveform(7, 1, 0, 0), waveform(8, 1, 0, 0)))

    def test_adc_range_and_quantization(self):
        for label in range(4):
            x = waveform(7, 1, label, 0)
            self.assertTrue(np.all((x > 0) & (x < 3.3)))
            np.testing.assert_allclose(x/LSB-.5, np.round(x/LSB-.5), atol=1e-10)

    def test_features_are_finite_for_constant_input(self):
        value = features(np.ones(SAMPLES)*1.65)
        self.assertEqual(len(value), len(FEATURES))
        self.assertTrue(np.isfinite(value).all())
        self.assertEqual(value[FEATURES.index("longest_flat_fraction")], 1)

    def test_frequency_feature_finds_known_tone(self):
        x = 1.65 + .3*np.sin(2*np.pi*125*np.arange(SAMPLES)/FS)
        self.assertEqual(features(x)[FEATURES.index("dominant_hz")], 125)

    def test_spectral_features_ignore_dc_bias(self):
        x = waveform(7, 1, 0, 0)
        a, b = features(x), features(x+.1)
        for name in ['dominant_hz','spectral_centroid_hz','high_band_fraction','spectral_entropy']:
            self.assertAlmostEqual(a[FEATURES.index(name)], b[FEATURES.index(name)], places=8)

    def test_dropout_inserts_long_flat_segment(self):
        f = features(waveform(7, 1, 2, 0))
        self.assertGreaterEqual(f[FEATURES.index('longest_flat_fraction')], 42/SAMPLES)

    def test_bad_input_shape_and_values(self):
        for x in [np.zeros(12), np.full(SAMPLES, np.nan)]:
            with self.assertRaises(ValueError): features(x)


class EvaluationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.x, cls.y, cls.groups, cls.waves = make_dataset(7, range(10), 2)

    def test_device_split_is_disjoint_and_complete(self):
        split = split_devices()
        sets = [set(v) for v in split.values()]
        self.assertFalse(sets[0] & sets[1] or sets[0] & sets[2] or sets[1] & sets[2])
        self.assertEqual(set.union(*sets), set(range(40)))
        self.assertEqual([len(x) for x in split.values()], [24, 8, 8])

    def test_each_device_has_balanced_classes(self):
        for device in range(10):
            np.testing.assert_array_equal(np.bincount(self.y[self.groups==device]), [2]*4)

    def test_features_exclude_labels_and_device_ids(self):
        self.assertEqual(self.x.shape, (80, len(FEATURES)))
        self.assertNotIn('device', FEATURES); self.assertNotIn('label', FEATURES)
        np.testing.assert_allclose(self.x[3], features(self.waves[3]))

    def test_scaler_is_fitted_on_training_records_only(self):
        train = self.groups < 6
        pipeline = models()['Logistic regression']
        pipeline.fit(self.x[train], self.y[train])
        np.testing.assert_allclose(pipeline[0].mean_, self.x[train].mean(axis=0))
        self.assertFalse(np.allclose(pipeline[0].mean_, self.x.mean(axis=0)))

    def test_dummy_is_25_percent_on_balanced_data(self):
        dummy = models()['Dummy'].fit(self.x, self.y)
        self.assertEqual(scores(self.y, dummy.predict(self.x))['accuracy'], .25)

    def test_metrics_for_perfect_predictions(self):
        self.assertEqual(scores(np.arange(4), np.arange(4)), {'accuracy':1.,'macro_f1':1.})

    def test_model_predictions_use_known_classes(self):
        for name, model in models().items():
            model.fit(self.x, self.y)
            self.assertTrue(set(model.predict(self.x[:5])).issubset(range(4)), name)

    def test_noise_shift_preserves_labels_and_group_ids(self):
        _, y, g, waves = make_dataset(7, range(10), 2, 5)
        np.testing.assert_array_equal(y, self.y); np.testing.assert_array_equal(g, self.groups)
        self.assertFalse(np.array_equal(waves, self.waves))

    def test_invalid_dataset_settings(self):
        with self.assertRaises(ValueError): split_devices(3)
        with self.assertRaises(ValueError): make_dataset(windows=0)
        with self.assertRaises(ValueError): make_dataset(devices=[])


if __name__ == '__main__': unittest.main()
