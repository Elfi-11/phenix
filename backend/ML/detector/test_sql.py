import contextlib
import copy
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import quote_plus

import joblib
import numpy as np
import pandas as pd
from detector.sql import generate, load_dataset, train, score, texts, normalize_query, choose_threshold

class SQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.root=Path(cls.tmp.name)
        protocol=[('train',40),('calibration',20),('validation',20),('test',20)]
        with patch('detector.sql.PROTOCOL',protocol):
            cls.manifest=generate(cls.root/'a',seed=19)
            generate(cls.root/'b',seed=19)
        cls.parts,_=load_dataset(cls.root/'a')
        with contextlib.redirect_stdout(io.StringIO()):cls.report=train(cls.root/'a',cls.root/'model')

    @classmethod
    def tearDownClass(cls):cls.tmp.cleanup()

    def test_reproducibility_and_separate_templates(self):
        for name in ['waf.log','waf.csv','annotations.csv','manifest.json']:
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())
        seen=set()
        for name,part in self.parts.items():
            self.assertEqual(set(part.is_attack),{0,1})
            self.assertEqual(set(part.loc[part.is_attack==1,'scenario']),{'boolean','union','comment','time','metadata'})
            templates=set(part.loc[part.is_attack==1,'template_id'])
            self.assertFalse(seen & templates);seen|=templates

    def test_normalization_and_no_identifier_features(self):
        value="q=Success'  UNION select NULL --"
        self.assertEqual(normalize_query(value),normalize_query(quote_plus(quote_plus(value))))
        frame=self.parts['validation'].copy();expected=texts(frame)
        for field in ['client_ip','status','request_target','scenario','template_id','is_attack','session_id']:
            frame[field]='changed'
        self.assertEqual(texts(frame),expected)
        with self.assertRaises(ValueError):normalize_query(None)
        with self.assertRaises(ValueError):normalize_query('x'*16385)

    def test_threshold_only_calibration_budget(self):
        y=[0,0,1,1];s=[.1,.2,.7,.9]
        threshold=choose_threshold(y,s,max_fpr=0)
        self.assertLessEqual(np.mean((np.array(s)>threshold)[np.array(y)==0]),0)
        self.assertEqual(np.mean((np.array(s)>threshold)[np.array(y)==1]),1)
        with self.assertRaises(ValueError):choose_threshold([0,0],[.1,.2])

    def test_validation_labels_and_test_do_not_fit_model(self):
        parts=copy.deepcopy(self.parts)
        parts['test']['query']=None
        parts['validation']['is_attack']=1-parts['validation']['is_attack']
        with patch('detector.sql.load_dataset',return_value=(parts,self.manifest)):
            with contextlib.redirect_stdout(io.StringIO()):report=train('unused',self.root/'second')
        self.assertEqual(report['metadata']['threshold'],self.report['metadata']['threshold'])
        a=joblib.load(self.root/'model/model.joblib')['model'];b=joblib.load(self.root/'second/model.joblib')['model']
        self.assertEqual(a.named_steps['tfidfvectorizer'].vocabulary_,b.named_steps['tfidfvectorizer'].vocabulary_)
        np.testing.assert_allclose(a.predict_proba(texts(self.parts['validation'])),b.predict_proba(texts(self.parts['validation'])))
        self.assertNotIn('test',report['splits'])
        self.assertFalse((self.root/'second/test_predictions.csv').exists())

    def test_source_integrity(self):
        p=self.root/'a/waf.csv';original=p.read_bytes()
        try:
            p.write_bytes(original+b'\n')
            with self.assertRaises(ValueError):load_dataset(self.root/'a')
        finally:p.write_bytes(original)

    def test_inference_without_labels_and_preserve_artifacts(self):
        csv=self.root/'real-format.csv'
        self.parts['validation'].drop(columns=['split','session_id','scenario','template_id','is_attack']).to_csv(csv,index=False)
        with contextlib.redirect_stdout(io.StringIO()):score(csv,self.root/'model/model.joblib',self.root/'scored.csv')
        result=pd.read_csv(self.root/'scored.csv')
        self.assertEqual(len(result),len(self.parts['validation']))
        self.assertNotIn('is_attack',result)
        self.assertTrue((self.root/'scored.detections.jsonl').exists())
        with self.assertRaises(ValueError):score(csv,self.root/'model/model.joblib',self.root/'scored.csv')
        with self.assertRaises(ValueError):train(self.root/'a',self.root/'model')
        with self.assertRaises(ValueError):generate(self.root/'a')

    def test_metric_counts(self):
        pred=pd.read_csv(self.root/'model/validation_predictions.csv')
        for name,mask in [('true_positive',(pred.is_attack==1)&(pred.predicted_sql==1)),
                          ('false_negative',(pred.is_attack==1)&(pred.predicted_sql==0)),
                          ('false_positive',(pred.is_attack==0)&(pred.predicted_sql==1))]:
            self.assertEqual(self.report['splits']['validation'][name],int(mask.sum()))

if __name__=='__main__':unittest.main()
