import csv
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import io
import json
from urllib.parse import urlsplit, parse_qs
from detector.collect import parse_access, time_ns, fetch_range, write_rows, request_page

LINE = '172.26.0.1 - - [21/Oct/2026:13:41:56 +0000] "GET /api/attackme/search?q=SUCCESS HTTP/1.1" 200 2 "-" "Browser" "127.0.0.1"'

class CollectTests(unittest.TestCase):
    def test_real_format(self):
        row = parse_access('2026-10-21 15:41:56.110\t' + LINE, {'service': 'waf'}, '123')
        self.assertEqual(row['observed_at'], '2026-10-21T13:41:56+00:00')
        self.assertEqual(row['client_ip'], '127.0.0.1')
        self.assertEqual(row['peer_ip'], '172.26.0.1')
        self.assertEqual(row['response_bytes'], 2)
        self.assertEqual(row['query'], 'q=SUCCESS')
        self.assertEqual(row['loki_timestamp_ns'], '123')

    def test_encoded_target_unchanged(self):
        row = parse_access(LINE.replace('SUCCESS', '%27+OR+1%3D1--'))
        self.assertEqual(row['query'], 'q=%27+OR+1%3D1--')

    def test_timezones(self):
        self.assertEqual(time_ns('2026-10-21T15:41:56+02:00'), time_ns('2026-10-21T13:41:56Z'))
        with self.assertRaises(ValueError): time_ns('2026-10-21T13:41:56')

    def test_no_silent_truncation_or_deduplication(self):
        logs = [(10, LINE, {}), (10, LINE, {}), (11, LINE, {}), (15, LINE, {}), (19, LINE, {})]
        def page(base, query, lo, hi, limit, timeout):
            return [row for row in logs if lo <= row[0] < hi][:limit]
        self.assertEqual(fetch_range('http://loki', '{}', 10, 20, limit=3, page=page), logs)
        with self.assertRaises(ValueError): fetch_range('http://loki', '{}', 10, 20, limit=2, page=page)

    def test_half_open_boundaries_and_empty(self):
        def page(base, query, lo, hi, limit, timeout):
            return [(n, LINE, {}) for n in range(lo, hi)][:limit]
        self.assertEqual([r[0] for r in fetch_range('http://loki', '{}', 1, 5, limit=3, page=page)], [1,2,3,4])
        self.assertEqual(fetch_range('http://loki', '{}', 1, 5, page=lambda *a: []), [])

    def test_invalid_input_no_partial_file_no_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            out=Path(tmp)/'logs.csv'
            with self.assertRaises(ValueError): write_rows([(LINE, {}, None), ('invalid', {}, None)], out)
            self.assertFalse(out.exists())
            write_rows([(LINE, {}, None)], out)
            with out.open() as handle:
                self.assertEqual(len(list(csv.DictReader(handle))), 1)
            with self.assertRaises(FileExistsError): write_rows([], out)

    def test_http_contract(self):
        payload={'status':'success','data':{'resultType':'streams','result':[{'stream':{'service':'waf'}, 'values':[['10', LINE]]}]}}
        with patch('detector.collect.urlopen', return_value=io.BytesIO(json.dumps(payload).encode())) as request:
            rows=request_page('http://loki:3100','{service="waf"}',1,20,1000,5)
            self.assertEqual(len(rows),1)
            params=parse_qs(urlsplit(request.call_args.args[0].full_url).query)
            self.assertEqual(params['direction'],['forward'])
            self.assertEqual(params['query'],['{service="waf"}'])
            self.assertEqual(request.call_args.kwargs['timeout'],5)

if __name__=='__main__': unittest.main()