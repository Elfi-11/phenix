import unittest
import joblib
import tempfile
from pathlib import Path
import numpy as np
import pandas as pd
from detector.context import ContextDetector
from detector.__main__ import FEATURES

class ContextTests(unittest.TestCase):
    def setUp(self):
        rng = np.random.default_rng(7)
        traffic = rng.uniform(5, 80, 500)
        self.frame = pd.DataFrame({FEATURES[0]: traffic})
        for i, col in enumerate(FEATURES[1:]):
            self.frame[col] = 2 + traffic * (i + 1) / 10 + rng.normal(0, .2, len(traffic))

    def test_labels_unused_and_batch_independent(self):
        a = ContextDetector().fit(self.frame.assign(is_anomaly=0))
        b = ContextDetector().fit(self.frame.assign(is_anomaly=1))
        np.testing.assert_allclose(a.score_samples(self.frame), b.score_samples(self.frame))
        np.testing.assert_allclose(a.score_samples(self.frame.iloc[:1]), a.score_samples(self.frame)[:1])

    def test_unexpected_latency_increases_score(self):
        model = ContextDetector().fit(self.frame)
        changed = self.frame.copy()
        changed['latency_ms'] += 100
        self.assertGreater(np.median(model.score_samples(changed)), np.median(model.score_samples(self.frame)) * 10)

    def test_serialization(self):
        model = ContextDetector().fit(self.frame)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'model.joblib'
            joblib.dump(model, path)
            restored = joblib.load(path)
            np.testing.assert_allclose(model.score_samples(self.frame), restored.score_samples(self.frame))

if __name__ == '__main__':
    unittest.main()
