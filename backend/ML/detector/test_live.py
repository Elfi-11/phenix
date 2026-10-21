import unittest
import numpy as np
import sklearn
from detector.live import detect
from detector.sql import SCHEMA

LINE='172.26.0.1 - - [21/Oct/2026:13:41:56 +0000] "GET /api/attackme/search?q=SUCCESS HTTP/1.1" 200 2 "-" "Browser" "192.0.2.50"'
class FakeModel:
    def predict_proba(self,values):
        return np.array([[.1,.9] for _ in values])

class LiveTests(unittest.TestCase):
    def setUp(self):
        self.bundle={'model':FakeModel(),'metadata':{'feature_schema':SCHEMA,'threshold':.8,'versions':{'sklearn':sklearn.__version__}}}

    def test_stable_identity_and_ml_provenance(self):
        first=detect(self.bundle,[(123,LINE,{'service':'waf','container':'phenix-waf-1'})])[0]
        second=detect(self.bundle,[(123,LINE,{'container':'phenix-waf-1','service':'waf'})])[0]
        self.assertEqual(first['detection_id'],second['detection_id'])
        self.assertEqual(first['source'],'ML')
        self.assertEqual(first['ip'],'192.0.2.50')
        self.assertEqual(first['peer_ip'],'172.26.0.1')
        self.assertNotEqual(first['detection_id'],detect(self.bundle,[(124,LINE,{})])[0]['detection_id'])
        self.assertNotIn('request_target',first)

    def test_threshold_empty_and_invalid_input(self):
        self.assertEqual(detect(self.bundle,[]),[])
        self.bundle['metadata']['threshold']=.9
        self.assertEqual(detect(self.bundle,[(123,LINE,{})]),[])
        with self.assertRaises(ValueError):detect(self.bundle,[(123,'not an access log',{})])

    def test_incompatible_model_refused(self):
        self.bundle['metadata']['feature_schema']='old-model'
        with self.assertRaises(ValueError):detect(self.bundle,[])

if __name__=='__main__':unittest.main()
