"""Valider le déclenchement HTTP frais et le code de sortie lu par Ansible."""
import contextlib
import io
import json
import threading
import unittest
import urllib.request
from unittest.mock import patch
from http.server import ThreadingHTTPServer
import selftest


class HTTPTests(unittest.TestCase):
    def setUp(self):
        self.server=ThreadingHTTPServer(('127.0.0.1',0),selftest.StatusHandler)
        self.port=self.server.server_port
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.stop)

    def stop(self):
        self.server.shutdown();self.server.server_close();self.thread.join(timeout=2)

    def test_fresh_success_is_required(self):
        with patch.object(selftest,'STATUS_PORT',self.port),patch.object(selftest,'un_paiement',return_value={'ok':True,'detail':'new'}) as probe,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(selftest.verify_once(),0)
        probe.assert_called_once_with(require_fresh=True)

    def test_old_green_does_not_hide_failed_fresh_test(self):
        selftest._etat={'ok':True,'detail':'old'}
        with patch.object(selftest,'STATUS_PORT',self.port),patch.object(selftest,'un_paiement',return_value={'ok':False,'detail':'fresh failed'}) as probe,contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(selftest.verify_once(),1)
        probe.assert_called_once_with(require_fresh=True)

    def test_dashboard_status_keeps_original_contract(self):
        selftest._etat={'ok':True,'http_status':201,'at':'now','detail':'OK'}
        with urllib.request.urlopen(f'http://127.0.0.1:{self.port}/status') as response:
            body=json.load(response)
        self.assertEqual(body,selftest._etat)


if __name__=='__main__':
    unittest.main()
