import csv
import tempfile
from pathlib import Path
import unittest
from detector.generate_waf import generate
from detector.collect import parse_access

class GeneratorTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.root = Path(cls.tmp.name)
        cls.manifest = generate(cls.root/'a', seed=7, requests_per_session=10)
        generate(cls.root/'b', seed=7, requests_per_session=10)
        with (cls.root/'a/waf.csv').open() as f: cls.rows=list(csv.DictReader(f))
        with (cls.root/'a/annotations.csv').open() as f: cls.labels=list(csv.DictReader(f))
    @classmethod
    def tearDownClass(cls): cls.tmp.cleanup()

    def test_reproducible(self):
        for name in ['waf.log','waf.csv','annotations.csv','manifest.json']:
            self.assertEqual((self.root/'a'/name).read_bytes(),(self.root/'b'/name).read_bytes())

    def test_same_parser_and_row_identity(self):
        lines=(self.root/'a/waf.log').read_text().splitlines()
        self.assertEqual(len(lines),2600)
        for line,row,label in zip(lines,self.rows,self.labels):
            self.assertEqual(parse_access(line)['request_target'],row['request_target'])
            self.assertEqual(row['loki_timestamp_ns'],label['loki_timestamp_ns'])
        self.assertEqual(len({r['loki_timestamp_ns'] for r in self.rows}), len(self.rows))

    def test_partitions_and_holdout_families(self):
        groups={s:[r for r in self.labels if r['split']==s] for s in ['train','calibration','validation','test']}
        for s in ['train','calibration']:
            self.assertTrue(all(r['is_attack']=='0' for r in groups[s]))
        self.assertEqual({r['scenario'] for r in groups['validation'] if r['is_attack']=='1'}, {'boolean','union'})
        self.assertEqual({r['scenario'] for r in groups['test'] if r['is_attack']=='1'}, {'comment','boolean_nested'})
        sessions=[{r['session_id'] for r in groups[s]} for s in groups]
        for i,a in enumerate(sessions):
            for b in sessions[i+1:]: self.assertFalse(a & b)

    def test_labels_separate_and_benign_encoded_queries(self):
        self.assertNotIn('is_attack', self.rows[0])
        normal=[r for r,a in zip(self.rows,self.labels) if a['is_attack']=='0']
        self.assertTrue(any('%27' in r['query'] for r in normal))
        self.assertTrue(any(r['status']=='403' for r in normal))
        self.assertTrue(any(r['path']=='/api/attackme/search' for r in normal))

    def test_no_overwrite_and_minimum_size(self):
        with self.assertRaises(ValueError):generate(self.root/'a')
        with self.assertRaises(ValueError):generate(self.root/'bad', requests_per_session=1)

if __name__=='__main__': unittest.main()