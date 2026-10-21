"""Contrôles hors réseau : fenêtres, sélection des routes et décision du modèle."""
import unittest
import numpy as np
import sklearn
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.linear_model import LogisticRegression
from detector.bruteforce import FEATURES, SCHEMA, NS, features, synthetic, detect


def line(status=401, target='/api/auth/login', ip='192.0.2.50'):
    return f'172.26.0.1 - - [21/Oct/2026:20:00:00 +0000] "POST {target} HTTP/1.1" {status} 30 "-" "test" "{ip}"'


class BruteForceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        x, y = synthetic(81, 6000)
        model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=1000, class_weight='balanced', random_state=81)).fit(x, y)
        cls.bundle = {'model': model, 'schema': SCHEMA, 'features': FEATURES, 'threshold': .7972798415566481, 'sklearn': sklearn.__version__}

    def test_features_with_success_and_failure(self):
        self.assertEqual(features([0, 10 * NS], [200, 401]), [2, 1, .5, .1])

    def test_recent_burst_detected_old_events_excluded(self):
        logs = [(str((60+i)*NS), line(), {}) for i in range(30)]
        alerts = detect(self.bundle, logs, 100*NS)
        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0]['ip'], '192.0.2.50')
        self.assertEqual(detect(self.bundle, logs, 200*NS), [])

    def test_success_and_other_route_do_not_alert(self):
        logs = [(str((60+i)*NS), line(200), {}) for i in range(30)]
        self.assertEqual(detect(self.bundle, logs, 100*NS), [])
        logs = [(str((60+i)*NS), line(401, '/api/accounts/me'), {}) for i in range(30)]
        self.assertEqual(detect(self.bundle, logs, 100*NS), [])

    def test_same_log_identity_and_no_cross_ip_pooling(self):
        logs = [(str((60+i)*NS), line(), {}) for i in range(30)]
        self.assertEqual(detect(self.bundle, logs, 100*NS)[0]['detection_id'], detect(self.bundle, logs, 101*NS)[0]['detection_id'])
        separate = [(str((60+i)*NS), line(ip=f'192.0.2.{i+1}'), {}) for i in range(30)]
        self.assertEqual(detect(self.bundle, separate, 100*NS), [])

    def test_deterministic_independent_splits(self):
        a, y = synthetic(81, 100); b, z = synthetic(81, 100); c, _ = synthetic(82, 100)
        np.testing.assert_array_equal(a, b); np.testing.assert_array_equal(y, z)
        self.assertFalse(np.array_equal(a, c))
