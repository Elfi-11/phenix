"""Contrôler le raccordement partagé sans réseau ni action réelle."""
import unittest
from unittest.mock import patch
from detector import live_combined as live


class CombinedTests(unittest.TestCase):
    def test_both_models_receive_same_logs_and_keep_their_threshold(self):
        logs = [('123', 'line', {})]
        sql = {'detection_id':'x', 'loki_timestamp_ns':'123', 'sql_score':.9, 'threshold':.1}
        brute = {'detection_id':'x', 'loki_timestamp_ns':'123', 'bruteforce_score':.95, 'threshold':.8}
        with patch.object(live, 'detect_sql', return_value=[sql]) as a, patch.object(live, 'detect_bruteforce', return_value=[brute]) as b:
            result=live.detect('sql-model','brute-model',logs,456)
            a.assert_called_once_with('sql-model',logs)
            b.assert_called_once_with('brute-model',logs,456)
        self.assertEqual(result['scanned'],1)
        self.assertEqual(result['counts'],{'sql_injection':1,'bruteforce':1})
        self.assertEqual(len({x['detection_id'] for x in result['alerts']}),2)
        self.assertEqual({x['threshold'] for x in result['alerts']},{.1,.8})
        self.assertNotIn('detection_kind',sql)

    def test_model_failure_is_not_hidden(self):
        with patch.object(live,'detect_sql',return_value=[]),patch.object(live,'detect_bruteforce',side_effect=ValueError('incompatible')):
            with self.assertRaises(ValueError):live.detect({}, {}, [], 123)

    def test_one_collection_for_two_models(self):
        import json,io,contextlib
        with patch('sys.argv',['live','--sql-model','sql','--brute-model','brute','--start-ns','1','--end-ns','100000000000']), \
             patch.object(live.joblib,'load',side_effect=[{},{}]), \
             patch.object(live,'fetch_range',return_value=[]) as fetch, \
             patch.object(live,'detect',return_value={'scanned':0,'alerts':[]}), \
             contextlib.redirect_stdout(io.StringIO()) as out:
            live.main()
        fetch.assert_called_once()
        self.assertEqual(json.loads(out.getvalue())['scanned'],0)
