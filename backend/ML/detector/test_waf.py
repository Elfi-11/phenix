import contextlib
import copy
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import joblib
import numpy as np
import pandas as pd
from detector.generate_waf import generate
from detector.waf import FEATURES, extract_features, load_dataset, query_features, read_requests, score, train

class WafTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory()
        cls.root=Path(cls.tmp.name)
        with patch('detector.generate_waf.PROTOCOL', [('train',60),('calibration',10),('validation',8),('test',8)]):
            generate(cls.root/'dataset', seed=17, requests_per_session=10)
        cls.parts,cls.manifest=load_dataset(cls.root/'dataset')
        with contextlib.redirect_stdout(io.StringIO()):
            cls.report=train(cls.root/'dataset',cls.root/'model')

    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_features_ignore_identifiers_labels_status(self):
        frame=self.parts['validation'].copy()
        before=extract_features(frame)
        for key in ['client_ip','request_target','status','scenario','is_attack','observed_at','session_id']:
            frame[key]='MODIFIED'
        pd.testing.assert_frame_equal(before,extract_features(frame))
        self.assertEqual(list(before.columns),FEATURES)
        self.assertTrue(np.isfinite(before.to_numpy()).all())

    def test_encoding_and_no_keyword_rule(self):
        self.assertEqual(query_features('q=%2527')['quote_count'],1)
        self.assertEqual(query_features('q=a+b')['space_count'],1)
        np.testing.assert_allclose(list(query_features('q=UNION').values()),list(query_features('q=NOINU').values()))
        self.assertTrue(all(np.isfinite(v) for v in query_features('').values()))
        with self.assertRaises(ValueError):query_features(None)
        with self.assertRaises(ValueError):query_features('a'*16385)

    def test_no_test_scoring_and_no_training_leak(self):
        self.assertNotIn('test', self.report['splits'])
        self.assertFalse((self.root/'model/test_predictions.csv').exists())
        parts=copy.deepcopy(self.parts)
        # Valeur impossible à transformer : l'essai doit réussir car le test n'est pas scoré.
        parts['test']['query']=None
        # Les labels de validation ne doivent pas influencer modèle ou seuil.
        parts['validation']['is_attack']=1-parts['validation']['is_attack']
        with patch('detector.waf.load_dataset',return_value=(parts,self.manifest)):
            with contextlib.redirect_stdout(io.StringIO()): report=train('unused',self.root/'second')
        self.assertEqual(report['metadata']['threshold'],self.report['metadata']['threshold'])
        a=joblib.load(self.root/'model/model.joblib')['model']
        b=joblib.load(self.root/'second/model.joblib')['model']
        x=extract_features(self.parts['validation'])
        np.testing.assert_allclose(a.score_samples(x),b.score_samples(x))

    def test_hash_mismatch_rejected(self):
        path=self.root/'dataset/waf.csv'
        original=path.read_bytes()
        try:
            path.write_bytes(original+b'\n')
            with self.assertRaises(ValueError):load_dataset(self.root/'dataset')
        finally:path.write_bytes(original)

    def test_score_without_annotations_and_no_overwrite(self):
        csv_path=self.root/'requests.csv'
        self.parts['validation'].drop(columns=['split','session_id','scenario','is_attack']).to_csv(csv_path,index=False)
        with contextlib.redirect_stdout(io.StringIO()):
            score(csv_path,self.root/'model/model.joblib',self.root/'scores.csv')
        scored=pd.read_csv(self.root/'scores.csv')
        self.assertEqual(len(scored),len(self.parts['validation']))
        self.assertNotIn('is_attack',scored)
        with self.assertRaises(ValueError):score(csv_path,self.root/'model/model.joblib',self.root/'scores.csv')
        with self.assertRaises(ValueError):train(self.root/'dataset',self.root/'model')

    def test_metrics_match_predictions(self):
        pred=pd.read_csv(self.root/'model/validation_predictions.csv')
        expected=self.report['splits']['validation']
        self.assertEqual(expected['true_positive'],int(((pred.is_attack==1)&(pred.predicted_anomaly==1)).sum()))
        self.assertEqual(expected['false_negative'],int(((pred.is_attack==1)&(pred.predicted_anomaly==0)).sum()))
        self.assertIsNone(self.report['splits']['train']['recall'])

if __name__=='__main__': unittest.main()
