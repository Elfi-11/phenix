"""Tests du contrat de données et de la séparation apprentissage/inférence."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest

import joblib
import numpy as np
import pandas as pd

from detector.__main__ import FEATURES, load_data, score, split_data

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'data/alphapay_telemetry_fr_realistic.csv'
ARTIFACT = ROOT / 'experiments/synthetic-v1/model.joblib'


class DetectorTests(unittest.TestCase):
    def test_split_has_no_overlap_and_training_is_normal(self):
        df = load_data(DATA, labelled=True)
        parts = split_data(df)
        self.assertEqual([len(x) for x in parts.values()], [5760, 5760, 4320, 4320])
        self.assertEqual(parts['train'].is_anomaly.sum(), 0)
        for a, b in zip(list(parts.values()), list(parts.values())[1:]):
            self.assertLess(a.timestamp.max(), b.timestamp.min())

    def test_missing_measurement_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            df = pd.read_csv(DATA).head(2)
            df.loc[0, 'cpu_usage_pct'] = np.nan
            p = Path(d) / 'bad.csv'; df.to_csv(p, index=False)
            with self.assertRaises(ValueError): load_data(p)

    def test_gap_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            df = pd.read_csv(DATA).head(3).iloc[[0, 2]]
            p = Path(d) / 'gap.csv'; df.to_csv(p, index=False)
            with self.assertRaises(ValueError): load_data(p)

    def test_training_anomaly_is_not_silently_removed(self):
        df = load_data(DATA, labelled=True)
        df.loc[0, 'is_anomaly'] = 1
        with self.assertRaises(ValueError): split_data(df)

    def test_no_label_or_integrity_feature(self):
        self.assertNotIn('is_anomaly', FEATURES)
        self.assertNotIn('timestamp', FEATURES)
        self.assertNotIn('balance_integrity_status', FEATURES)
        bundle = joblib.load(ARTIFACT)
        self.assertEqual(list(bundle['model'].feature_names_in_), FEATURES)

    def test_inference_does_not_use_labels_and_matches_saved_test(self):
        with tempfile.TemporaryDirectory() as d, contextlib.redirect_stdout(io.StringIO()):
            test = split_data(load_data(DATA, labelled=True))['test']
            p = Path(d) / 'input.csv'
            test.drop(columns=['is_anomaly', 'balance_integrity_status']).to_csv(p, index=False)
            out = Path(d) / 'scores.csv'
            score(p, ARTIFACT, out)
            obtained = pd.read_csv(out)
            expected = pd.read_csv(ROOT / 'experiments/synthetic-v1/test_predictions.csv')
            np.testing.assert_allclose(obtained.anomaly_score, expected.anomaly_score, atol=1e-12)
            np.testing.assert_array_equal(obtained.predicted_anomaly, expected.predicted_anomaly)
            test['is_anomaly'] = 1 - test.is_anomaly
            test.to_csv(p, index=False)
            out2 = Path(d) / 'scores2.csv'; score(p, ARTIFACT, out2)
            np.testing.assert_array_equal(pd.read_csv(out2).predicted_anomaly, obtained.predicted_anomaly)


if __name__ == '__main__': unittest.main()