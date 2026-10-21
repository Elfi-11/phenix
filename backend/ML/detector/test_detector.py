"""Tests autonomes : aucun artefact d'expérience n'est requis dans Git."""
import contextlib
import io
from pathlib import Path
import tempfile
import unittest
import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest
import sklearn

from detector.__main__ import FEATURES, load_data, split_data, score
from detector.generate import generate


class DetectorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data, cls.events = generate(20261021)

    def test_reproducibility(self):
        again, events = generate(20261021)
        pd.testing.assert_frame_equal(self.data, again)
        self.assertEqual(self.events, events)

    def test_split_and_no_training_anomalies(self):
        p = split_data(self.data, 10, 7, 5)
        self.assertEqual([len(x) for x in p.values()], [14400, 10080, 7200, 8640])
        self.assertEqual(p['train'].is_anomaly.sum(), 0)
        for a,b in zip(list(p.values()), list(p.values())[1:]):self.assertLess(a.timestamp.max(), b.timestamp.min())
        self.assertGreater(p['train'].req_per_sec.max(), 48)
        self.assertGreater(p['train'].cpu_usage_pct.max(), 52)

    def test_validation_changes_do_not_change_training(self):
        modified = self.data.copy()
        mask = modified.timestamp >= modified.timestamp.iloc[0] + pd.Timedelta(days=17)
        modified.loc[mask, 'req_per_sec'] *= 10
        original_parts = split_data(self.data, 10, 7, 5)
        changed_parts = split_data(modified, 10, 7, 5)
        for name in ['train','calibration']:pd.testing.assert_frame_equal(original_parts[name], changed_parts[name])

    def test_events_are_complete_and_separate(self):
        self.assertEqual(len(self.events), 12)
        labelled = set()
        for e in self.events:
            rows = self.data[self.data.timestamp.between(pd.Timestamp(e['start']), pd.Timestamp(e['end']))]
            self.assertEqual(len(rows), e['minutes'])
            self.assertTrue(rows.is_anomaly.eq(1).all())
            indices = set(rows.index)
            self.assertFalse(labelled & indices)
            labelled |= indices
        self.assertEqual(len(labelled), int(self.data.is_anomaly.sum()))

    def test_invalid_input_is_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            p = Path(folder)/'data.csv'
            bad = self.data.head(3).copy();bad.loc[0,'cpu_usage_pct']=np.nan;bad.to_csv(p,index=False)
            with self.assertRaises(ValueError):load_data(p)
            self.data.head(3).iloc[[0,2]].to_csv(p,index=False)
            with self.assertRaises(ValueError):load_data(p)
            self.data.head(3).drop(columns=['latency_ms']).to_csv(p,index=False)
            with self.assertRaises(ValueError):load_data(p)

    def test_inference_without_labels_and_no_overwrite(self):
        self.assertNotIn('is_anomaly', FEATURES)
        self.assertNotIn('balance_integrity_status', FEATURES)
        with tempfile.TemporaryDirectory() as folder, contextlib.redirect_stdout(io.StringIO()):
            folder=Path(folder)
            model=IsolationForest(n_estimators=10,random_state=42).fit(self.data.loc[:199,FEATURES])
            metadata={'features':FEATURES,'threshold':.6,'versions':{'sklearn':sklearn.__version__}}
            artifact=folder/'model.joblib';joblib.dump({'model':model,'metadata':metadata},artifact)
            data=folder/'input.csv';self.data.head(60)[['timestamp',*FEATURES]].to_csv(data,index=False)
            score(data,artifact,folder/'scores.csv')
            self.assertEqual(len(pd.read_csv(folder/'scores.csv')),60)
            with self.assertRaises(ValueError):score(data,artifact,folder/'scores.csv')

    def test_training_anomaly_refused(self):
        bad=self.data.copy();bad.loc[0,'is_anomaly']=1
        with self.assertRaises(ValueError):split_data(bad,10,7,5)

    def test_split_durations_validated(self):
        with self.assertRaises(ValueError):split_data(self.data,0,7,5)


if __name__=='__main__':unittest.main()
